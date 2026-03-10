import streamlit as st
import pandas as pd
import plotly.express as px  # <--- 必须有这一行，它是 px 的来源
import plotly.graph_objects as go # <--- 用于绘制雷达图
from datetime import datetime, date
import json
import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import red, HexColor  # 必须添加这行

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="欧图工厂生产流程审核系统",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.dialog("查看原图")
def show_full_image(image_path):
    st.image(image_path, use_container_width=True)

def inject_custom_css():
    st.markdown("""
        <style>
        [data-testid="stFileUploadDropzone"] div div { display: none !important; }
        [data-testid="stFileUploadDropzone"] { padding: 0px !important; min-height: 45px !important; border: 1px dashed #ccc; }
        .stPopover [data-testid="stBaseButton-secondary"] { width: 100%; }
        [data-testid="stExpander"] [data-testid="stVerticalBlock"] { gap: 0.2rem !important; }
        hr { margin: 0.4rem 0 !important; }
        </style>
    """, unsafe_allow_html=True)
# ==================== 字体配置 - 使用上传的SimSun.ttf ====================
def setup_chinese_font():
    font_path = os.path.join(os.path.dirname(__file__), "SimSun.ttf")
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('SimSun', font_path))
        return 'SimSun'
    else:
        st.warning("未找到SimSun.ttf字体文件，PDF中文可能显示异常")
        return 'Helvetica'

CHINESE_FONT = setup_chinese_font()

# ==================== 数据初始化 ====================
DATA_DIR = "data"
MEDIA_DIR = os.path.join(DATA_DIR, "media") # 新增：图片存储目录
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)

# ==================== 评分体系数据模型 ====================
class DataStore:
    def __init__(self):
        # 1. 工厂列表（后续可以移到 json 文件实现动态增删）
        self.factories = [{"id": 1, "name": "深圳XX服装厂"}, {"id": 2, "name": "广州XX制衣厂"}]
        
        # 2. 评分模块初始化
        self.modules = self._init_modules()
        
        # 3. 加载历史评估数据
        self.evaluations = self._load_evaluations()
        
        # 系统总分
        self.total_system_score = 177

    def verify_user(self, email, password):
        """
        终极验证逻辑
        """
        # 1. 预处理：去掉首尾空格，全部转为小写来对比
        input_id = email.strip().lower()
        input_pwd = password.strip()
        
        # 2. 验证管理员 (admin/sadmin)
        admin_pwds = st.secrets.get("password", {})
        # 将管理员账号也转小写对比
        admin_dict_lower = {str(k).lower(): str(v) for k, v in admin_pwds.items()}
        
        if input_id in admin_dict_lower:
            if input_pwd == admin_dict_lower[input_id]:
                role_name = "高级管理员" if input_id == "sadmin" else "管理员"
                return {"name": role_name, "role": input_id}
        
        # 3. 验证评估员
        evaluators = st.secrets.get("evaluators", {})
        # 将 Secrets 里的评估员 Email 全部转为小写
        eval_dict_lower = {str(k).lower(): str(v) for k, v in evaluators.items()}
        
        if input_id in eval_dict_lower:
            # 这里的规则：用你【原始输入】的账号（不带 strip/lower）拼接 123 
            # 还是用【处理后】的账号？
            # 建议用处理后的，最稳妥：
            expected_pwd = f"{input_id}123"
            
            # 如果还是不行，试试直接打印出期望的密码在后台日志里 (Streamlit Cloud 右下角 Manage app 可看)
            if input_pwd == expected_pwd:
                return {"name": eval_dict_lower[input_id], "role": "user"}
        
        return None

    def get_evaluations_by_user(self, user_id, role):
        """
        权限过滤逻辑：
        - 如果是 admin 或 sadmin，返回所有评估记录
        - 如果是普通 user，只返回 evaluator_id 等于自己账号的记录
        """
        if role in ["admin", "sadmin"]:
            return self.evaluations
        return [e for e in self.evaluations if e.get('evaluator_id') == user_id]

    def get_item_score(self, item_id):
        """数据分析辅助函数：根据ID获取小项分值"""
        for mod in self.modules.values():
            for sub in mod['sub_modules'].values():
                for it in sub['items']:
                    if it['id'] == item_id:
                        return it['score']
        return 0

    def _init_modules(self):
        return {
            "纸样、样衣制作": {
                "sub_modules": {
                    "1. 纸样开发标准": {
                        "items": [
                            {"id": "p1_1", "name": "① 使用CAD软件制作/修改纸样", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "p1_2", "name": "② 缝份清晰标记应合规", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "p1_3", "name": "③ 布纹线，剪口标注合规并清晰", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "p1_4", "name": "④ 放码标准（尺寸增量）遵守客户要求，并文档化", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "p1_5", "name": "⑤ 技术包（Tech Pack）应明确标注尺寸表、工艺说明与要求，及特殊工艺说明（尤其是特殊面料或设计）", "score": 3, "is_key": True, "details": [], "comment": ""},
                        ]
                    },
                    "2. 版本控制与追溯性": {
                        "items": [
                            {"id": "p2_1", "name": "① 纸样版本控制系统（确保最新、准确、可追溯）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "p2_2", "name": "② 文档记录：纸样历史、修订、批准", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "p2_3", "name": "③ 物理纸样（平放/悬挂）及数字备份的安全存储", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "3. 初版审核与文档化": {
                        "items": [
                            {"id": "p3_1", "name": "① 尺寸与工艺审核，应符合技术包要求（检验记录）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "p3_2", "name": "② 面辅料核对，并按要求进行功能性检测（检验记录）", "score": 3, "is_key": True, "details": [], "comment": ""},
                        ]
                    }
                }
            },
            "面辅料品质控制": {
                "sub_modules": {
                    "1. 面料仓库检查": {
                        "items": [
                            {"id": "m1_1", "name": "① 合格/不合格品/待检标识应明确，分开堆放", "score": 1, "is_key": False, "details": ["标识不明确", "未分开堆放"], "comment": ""},
                            {"id": "m1_2", "name": "② 面料不可“井”字堆放，高度不可过高（建议<1.5m）（针织面料除外）", "score": 1, "is_key": False, "details": ["面料井字堆放", "堆放高度过高"], "comment": ""},
                            {"id": "m1_3", "name": "③ 不同颜色及批次（缸号）分开堆放", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "m1_4", "name": "④ 托盘存放不靠墙、不靠窗、避光储存及防潮防霉", "score": 1, "is_key": False, "details": ["靠墙", "靠窗", "未避光储存", "未防潮防霉"], "comment": ""},
                            {"id": "m1_5", "name": "⑤ 温湿度计及记录（湿度<65%）", "score": 1, "is_key": False, "details": [], "comment": "监控湿度的变化，便于采取相应的解决方案（如抽湿）"},
                        ]
                    },
                    "2. 面料入库记录": {
                        "items": [
                            {"id": "m2_1", "name": "① 面料厂验布记录/测试记录/缸差布", "score": 1, "is_key": False, "details": ["无验布记录", "无测试记录", "无缸差布"], "comment": "测试记录和缸差布可预防面料品质问题和色差问题"},
                            {"id": "m2_2", "name": "② 入库单（卷数，米数，克重等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "3. 面料检验（织成试样检验）": {
                        "items": [
                            {"id": "m3_1", "name": "① 四分制验布及现场演示", "score": 1, "is_key": False, "details": ["无记录", "现场工人操作不规范"], "comment": ""},
                            {"id": "m3_2", "name": "② 500m以下全检，500m以上至少抽检10%（覆盖每缸）", "score": 3, "is_key": True, "details": ["500m以下未全检", "500m以上抽检不足10%"], "comment": ""},
                            {"id": "m3_3", "name": "③ 核对面料厂缸差布和大货面料（颜色D65，克重，防静电）", "score": 1, "is_key": False, "details": [], "comment": "缸差核对要在灯箱里进行，灯光要用D65光源"},
                        ]
                    },
                    "4. 面料测试": {
                        "items": [
                            {"id": "m4_1", "name": "① 每缸测试记录（如水洗色牢度，干湿色牢度，PH值）", "score": 1, "is_key": False, "details": [], "comment": "可以控制大货的色牢度，沾色等问题"},
                        ]
                    },
                    "5. 预缩记录和结果": {
                        "items": [
                            {"id": "m5_1", "name": "① 面料缩率要求 ≤ 3%（水洗针织款除外）", "score": 3, "is_key": True, "details": [], "comment": "面料缩率大于3%时，成衣工厂的尺寸控制难度较大"},
                            {"id": "m5_2", "name": "② 每缸缩率记录", "score": 3, "is_key": True, "details": [], "comment": "每缸缩率测试可以更好的控制大货成衣尺寸（纸版可以进行放缩率）"},
                        ]
                    },
                    "6. 面料出库记录及盘点记录": {
                        "items": [
                            {"id": "m6_1", "name": "① 出库记录含款号，缸号，米数，色号，时间，领料人等信息", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "m6_2", "name": "② 盘点记录", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "m6_3", "name": "③ 库存1年以上面料不可使用", "score": 1, "is_key": False, "details": [], "comment": "盘点一年以上的库存面料禁止使用（成衣撕裂牢度等会受影响）"},
                        ]
                    },
                    "7. 辅料仓库检查": {
                        "items": [
                            {"id": "m7_1", "name": "① 辅料存放标识明确（订单/款号/色号，分类堆放）", "score": 1, "is_key": False, "details": ["订单/款号/色号标识不清晰", "分类堆放标识不清晰"], "comment": "以防辅料发放错款"},
                            {"id": "m7_2", "name": "② 辅料入库记录（品类，数量）", "score": 1, "is_key": False, "details": ["无品类记录", "无数量记录"], "comment": ""},
                        ]
                    },
                    "8. 辅料检验": {
                        "items": [
                            {"id": "m8_1", "name": "① 正确辅料卡核对（型号，颜色，功能，内容，外观）", "score": 1, "is_key": False, "details": ["无型号", "无颜色", "无功能", "无内容", "无外观"], "comment": ""},
                        ]
                    },
                    "9. 辅料测试": {
                        "items": [
                            {"id": "m9_1", "name": "① 织带，橡筋，拉链，绳子的预缩测试（水洗缩，烫蒸缩）", "score": 3, "is_key": True, "details": [], "comment": "预防做到衣服上起皱，起浪等问题"},
                        ]
                    },
                    "10. 辅料出库记录及盘点记录": {
                        "items": [
                            {"id": "m10_1", "name": "① 出库记录含款号，数量，色号，时间，领料人等信息", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "m10_2", "name": "② 盘点记录", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "m10_3", "name": "③ 库存记录（保留至少1年）", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    }
                }
            },
            "产前会议控制": {
                "sub_modules": {
                    "1. 参会人员": {
                        "items": [
                            {"id": "pp1_1", "name": "① 技术部", "score": 1, "is_key": False, "details": [], "comment": "技术部对前期开发比较了解，可以规避打样时发生的问题，更好的控制大货品质"},
                            {"id": "pp1_2", "name": "② 质检部", "score": 1, "is_key": False, "details": [], "comment": "质量部门要跟进技术部提出的问题点及大货品质"},
                            {"id": "pp1_3", "name": "③ 业务部", "score": 1, "is_key": False, "details": [], "comment": "业务部门告知面辅料情况及订单进度"},
                            {"id": "pp1_4", "name": "④ 生产部（裁剪，生产主管，生产组长）", "score": 1, "is_key": False, "details": ["无裁剪", "无生产主管", "无生产组长"], "comment": ""},
                            {"id": "pp1_5", "name": "⑤ 后道（后道主管）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp1_6", "name": "⑥ 二次加工产品（印花/绣花/水洗/烫钻等）各工序负责人必须参会", "score": 1, "is_key": False, "details": [], "comment": "二次加工负责人主要时了解二次加工的产品如何控制品质"},
                        ]
                    },
                    "2. 工艺标准传达及预防措施": {
                        "items": [
                            {"id": "pp2_1", "name": "① 客户确认样", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp2_2", "name": "② 确认意见，明确客户要求", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp2_3", "name": "③ 试生产样（客户确认码，最小码及最大码）和封样", "score": 3, "is_key": True, "details": ["无客户确认码", "无最大码", "无最小码", "无封样"], "comment": "做最小码和最大码衣服，可提前预知大货可能出现的问题"},
                            {"id": "pp2_4_a", "name": "④ 工艺单需覆盖以下内容 a. 重点工序难点（制作领子，门襟等小样）及解决方案", "score": 1, "is_key": False, "details": [], "comment": "给车间生产员工一个质量标准参照"},
                            {"id": "pp2_4_b", "name": "⑤ 工艺单需覆盖以下内容 b. 试生产样的外观/尺寸/克重/试身的问题及解决方案", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp2_4_c", "name": "⑥ 工艺单需覆盖以下内容 c. 对条对格，花型定位等要求", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp2_4_d", "name": "⑦ 工艺单需覆盖以下内容 d. 特别关注撕裂强度的缝制工艺的风险", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp2_4_e", "name": "⑧ 工艺单需覆盖以下内容 e. 特别关注粘衬环节的风险（颜色差异，透胶，粘衬颜色）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp2_4_f", "name": "⑨ 工艺单需覆盖以下内容 f. 轻薄产品包装方法风险评估（皱，滑落等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "3. 技术难点分析": {
                        "items": [
                            {"id": "pp3_1", "name": "① 提出相应的改进建议", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp3_2", "name": "② 明确跟进人员及负责人", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "4. 会议记录执行": {
                        "items": [
                            {"id": "pp4_1", "name": "① 会议记录完整，参会人员签字确认", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "pp4_2", "name": "② 会议记录随工艺单确认样一起流转至生产各部门", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    }
                }
            },
            "裁剪品质控制": {
                "sub_modules": {
                    "1. 面料松布": {
                        "items": [
                            {"id": "c1_1", "name": "① 面料不可捆扎", "score": 1, "is_key": False, "details": [], "comment": "放缩后困扎面料，会影响面料的回缩"},
                            {"id": "c1_2", "name": "② 面料不可多卷混放", "score": 1, "is_key": False, "details": [], "comment": "多卷放在一起，会影响压在下方面料的回缩，敏感面料会产生压痕"},
                            {"id": "c1_3", "name": "③ 面料不可落地摆放", "score": 1, "is_key": False, "details": [], "comment": "预防脏污，潮湿等问题"},
                            {"id": "c1_4", "name": "④ 现场标识清晰（订单号，缸号/卷号，开始及结束时间）", "score": 3, "is_key": True, "details": ["订单号标识不清晰", "缸号/卷号不清晰", "开始及结束时间不清晰"], "comment": ""},
                        ]
                    },
                    "2. 待裁": {
                        "items": [
                            {"id": "c2_1", "name": "① 复核面料测试报告，松布时效", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c2_2", "name": "② 裁剪计划单及签字", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c2_3", "name": "③ 唛架的核对（是否缺失，对码）", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "3. 铺布": {
                        "items": [
                            {"id": "c3_1", "name": "① 确认铺布方式（单向/双向/定位），确保一件一方向", "score": 1, "is_key": False, "details": [], "comment": "预防大货有色差，色光"},
                            {"id": "c3_2", "name": "② 要求面料平整，无褶皱，无拉伸变形，无纬斜，且布边对齐", "score": 1, "is_key": False, "details": ["面料不平整有褶皱", "拉伸变形", "纬斜", "布边未对齐"], "comment": ""},
                            {"id": "c3_3", "name": "③ 铺布层数（50-80层）薄料高度<5cm，其他面料最高不能超过12cm（自动裁床根据裁床限定高度）", "score": 1, "is_key": False, "details": [], "comment": "控制裁片的精准度，（层高太高容易偏刀，尺寸控制不准确）"},
                            {"id": "c3_4", "name": "④ 每卷面料需要用隔层纸或面料隔开", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c3_5", "name": "⑤ 弹力面料铺布后须静置2小时", "score": 3, "is_key": True, "details": [], "comment": "以防铺布时把面料拉伸"},
                            {"id": "c3_6", "name": "⑥ 铺布完成后用夹子四周固定，中间用重物压实（自动裁床除外）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c3_7", "name": "⑦ 剩余面料布头需标识清晰以备换片", "score": 1, "is_key": False, "details": [], "comment": "控制换片导致色差"},
                        ]
                    },
                    "4. 裁片": {
                        "items": [
                            {"id": "c4_1", "name": "① 裁片大小的复核（上中下各3片）", "score": 3, "is_key": True, "details": [], "comment": "复核裁片的精准度"},
                            {"id": "c4_2", "name": "② 验片外观（布疵，勾丝，污渍，印花等）", "score": 3, "is_key": True, "details": [], "comment": ""},
                            {"id": "c4_3", "name": "③ 编号", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c4_4", "name": "④ 用捆扎绳卷筒式捆扎（捆扎绳有裁片信息：款号，分包号，件数，缸号，尺码等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c4_5", "name": "⑤ 分码分色存放（浅色需覆盖分开放置），禁止落地", "score": 1, "is_key": False, "details": ["裁片未分码分色存放", "裁片落地"], "comment": "预防沾色，脏污等"},
                        ]
                    },
                    "5. 粘衬": {
                        "items": [
                            {"id": "c5_1", "name": "① 粘衬机清洁和机器维护", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c5_2", "name": "② 粘衬机参数（衬厂提供）和工艺单吻合", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c5_3", "name": "③ 粘衬丝缕方向同面料丝缕方向", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "c5_4", "name": "④ 入粘衬机时按丝缕方向送入", "score": 1, "is_key": False, "details": [], "comment": "预防裁片粘衬后变形"},
                            {"id": "c5_5", "name": "⑤ 首批粘衬的裁片，需做剥离测试，是否透胶等评估风险（如有问题，立即会报裁剪主管跟进解决）", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    }
                }
            },
            "缝制工艺品质控制": {
                "sub_modules": {
                    "1. 缝制设备/特种设备": {
                        "items": [
                            {"id": "s1_1", "name": "① 定期维护保养记录", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s1_2", "name": "② 压脚类型与面料是否匹配", "score": 1, "is_key": False, "details": [], "comment": "控制缝制起皱，磨破面料等问题"},
                            {"id": "s1_3", "name": "③ 针距/针型号是否匹配", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s1_4", "name": "④ 缝纫线硅油用量及线迹张力核查（线迹平整度等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "2. 点位及小烫": {
                        "items": [
                            {"id": "s2_1", "name": "① 点位工序要点 a. 禁止使用高温消色笔", "score": 3, "is_key": True, "details": [], "comment": "高温消色笔在低温（零下）会显现出来"},
                            {"id": "s2_2", "name": "② 点位工序要点 b. 核查丝缕方向是否与纸样标注的方向一致", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s2_3", "name": "③ 点位工序要点 c. 点位前确保裁片和纸样吻合，避免偏移", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s2_4", "name": "④ 小烫工序要点 a. 烫台用白布包裹及台面干净整洁，定期更换", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s2_5", "name": "⑤ 小烫工序要点 b.烫斗温度和面料匹配（建议真丝面料低于110度）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s2_6", "name": "⑥ 小烫工序要点 c.烫工的操作手法是否正确（见指南）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s2_7", "name": "⑦ 查验 a. 查验是否有激光印/透胶", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s2_8", "name": "⑧ 查验 b. 查验是否变型/变色", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s2_9", "name": "⑨ 查验 c. 查验粘衬牢固度", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "3. 缝制中": {
                        "items": [
                            {"id": "s3_1", "name": "① 重点工序悬挂指示牌及标准小样（领子，口袋，门襟，袖口等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s3_2", "name": "② 重点工序是否有辅助工具提高质量稳定性（压脚，鱼骨，模版等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s3_3", "name": "③ 现场是否有首件样及资料（工艺单，辅料卡，产前会议记录等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s3_4", "name": "④ 线上车工技能评估（半成品的质量-皱/对称等）", "score": 3, "is_key": True, "details": [], "comment": ""},
                            {"id": "s3_5", "name": "⑤ 巡检是否定时巡查重点工序质量", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s3_6", "name": "⑥ 线头是否随做随剪", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s3_7", "name": "⑦ 半成品不可捆扎过紧，避免褶皱", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s3_8", "name": "⑧ 流转箱用布包裹，半成品分色分码区分", "score": 1, "is_key": False, "details": [], "comment": "预防半成品衣服在流转过程中勾纱，脏污"},
                        ]
                    },
                    "4. 线上检验": {
                        "items": [
                            {"id": "s4_1", "name": "① 尺寸检验 每色每码 >10% 并记录", "score": 3, "is_key": True, "details": [], "comment": ""},
                            {"id": "s4_2", "name": "② 外观检验 每色每码 > 10% 并记录", "score": 3, "is_key": True, "details": [], "comment": ""},
                            {"id": "s4_3", "name": "③ 试身小中大码和封样/首件样 对比外观及功能性（特别是重点工序），并记录", "score": 3, "is_key": True, "details": [], "comment": ""},
                            {"id": "s4_4", "name": "④ 中检合格品/非合格品分开摆放", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s4_5", "name": "⑤ 不合格品需立即退回对应工序翻修，并有组长跟进", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s4_6", "name": "⑥ 中检检验按工序记录疵点类型及比例，以便车工技能提升", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "5. 唛头": {
                        "items": [
                            {"id": "s5_1", "name": "① 按裁剪数量尺码数领取主标，尺码表，洗标", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s5_2", "name": "② 尺码表，洗标顺序不可错乱，以阅读方向缝制", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "s5_3", "name": "③ 一码一清，一款一清，如有剩余唛头，需追溯原因，并有组长跟进解决", "score": 1, "is_key": False, "details": [], "comment": "预防大货衣服错码"},
                        ]
                    }
                }
            },
            "后道品质控制": {
                "sub_modules": {
                    "1. 后道区域": {
                        "items": [
                            {"id": "f1_1", "name": "① 后道区域划分明确，并有清晰标识", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f1_2", "name": "② 中转箱需要明确标识", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f1_3", "name": "③ 样衣和资料悬挂在后道区域", "score": 1, "is_key": False, "details": [], "comment": "供后道核对品质和尺寸等"},
                        ]
                    },
                    "2. 锁眼钉扣": {
                        "items": [
                            {"id": "f2_1", "name": "① 按纸样点位，（禁止使用高温消色笔）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f2_2", "name": "② 每码一纸样，标识对应尺码", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f2_3", "name": "③ 核对锁眼纽扣的大小，位置；钉扣的牢度和纽扣的吻合度；锁眼线迹需干净整洁", "score": 1, "is_key": False, "details": ["大小/位置", "牢度和吻合度", "线迹不干净整洁"], "comment": ""},
                            {"id": "f2_4", "name": "④ 核查功能性", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "3. 整烫": {
                        "items": [
                            {"id": "f3_1", "name": "① 是否有摇臂烫台（胸省，袖笼等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f3_2", "name": "② 是否过度压烫，是否有激光印", "score": 1, "is_key": False, "details": ["过度压烫", "有激光印"], "comment": ""},
                            {"id": "f3_3", "name": "③ 整烫后合理放置（轻薄款建议悬挂防皱）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f3_4", "name": "④ 平放不易过高，底层不可以明显褶皱", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "4. 总检": {
                        "items": [
                            {"id": "f4_1", "name": "① 检验区域光源不得低于750LUX，温湿度计及记录（室内湿度超过65%，关注产品潮湿度）", "score": 1, "is_key": False, "details": ["光源低于750LUX", "无温湿度计及记录"], "comment": ""},
                            {"id": "f4_2", "name": "② 按码数100%检验（尺寸，标，外观，功能，湿度，试身效果等），后道主管/质量经理需抽查合格品（建议抽查每人员5%）", "score": 3, "is_key": True, "details": ["未按码数100%检验", "未按要求抽查"], "comment": ""},
                            {"id": "f4_3", "name": "③ 疵点问题需清晰标识", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f4_4", "name": "④ 待检品/合格品/不合格品分开放置", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f4_5", "name": "⑤ 污渍清理需在指定区域清理（确保返工后无水印，无变色，无异味）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f4_6", "name": "⑥ 总检跟踪翻修品，当天款当天结束", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f4_7", "name": "⑦ 总检汇总100%检验记录（报告）和疵点问题（建议汇总次品率），并反馈生产部门改进", "score": 3, "is_key": True, "details": [], "comment": "后续提升大货的品质的依据"},
                        ]
                    },
                    "5. 包装": {
                        "items": [
                            {"id": "f5_1", "name": "① 是否有标准包装样", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f5_2", "name": "② 分色分码分区包装（潮湿度需达到客户要求）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f5_3", "name": "③ 胶袋贴纸和裁剪数尺码吻合，一码一清，分码入筐", "score": 3, "is_key": True, "details": [], "comment": "预防包装错码"},
                            {"id": "f5_4", "name": "④ 一款一清，如有剩余贴纸，需追溯原因，并由组长跟进解决", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f5_5", "name": "⑤ 9点测试记录及检针报告", "score": 1, "is_key": False, "details": [], "comment": "控制衣服内的金属和安全性"},
                        ]
                    },
                    "6. 装箱": {
                        "items": [
                            {"id": "f6_1", "name": "① 按装箱单装箱（业务部门评估复核）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "f6_2", "name": "② 纸箱尺寸和质量是否按客人要求", "score": 1, "is_key": False, "details": ["尺寸不符合要求", "质量不符合要求"], "comment": ""},
                            {"id": "f6_3", "name": "③ 纸箱外观（不可鼓箱，不可超重，不可空箱）", "score": 1, "is_key": False, "details": ["鼓箱", "超重", "空箱"], "comment": ""},
                            {"id": "f6_4", "name": "④ 箱唛贴纸信息核对，里外一致（与箱单/订单）", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    }
                }
            },
            "质量部门品质控制": {
                "sub_modules": {
                    "1. AQL抽检": {
                        "items": [
                            {"id": "q1_1", "name": "① 按AQL4.0/L2检验", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    }
                }
            },
            "其他评分": {
                "sub_modules": {
                    "1. Dummy": {
                        "items": [
                            {"id": "o1_1", "name": "① 是否有标准Dummy", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "2. 利器管控": {
                        "items": [
                            {"id": "o2_1", "name": "① 是否专人专管（如裁剪刀等）", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "o2_2", "name": "② 是否有完整的换针记录", "score": 1, "is_key": False, "details": [], "comment": ""},
                            {"id": "o2_3", "name": "③ 小剪刀等是否捆绑固定", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    },
                    "3. 其他": {
                        "items": [
                            {"id": "o3_1", "name": "① 个人生活物品食物等禁止出现在生产区域", "score": 1, "is_key": False, "details": [], "comment": ""},
                        ]
                    }
                }
            }
        }
    def _load_evaluations(self):
        f = os.path.join(DATA_DIR, "evaluations.json")
        return json.load(open(f, 'r', encoding='utf-8')) if os.path.exists(f) else []

    def save_evaluation(self, ev, index=None):
    # """
    # 如果提供了 index，则覆盖旧记录（编辑模式）；
    # 否则追加新记录（新增模式）。
    # """
        if index is not None and 0 <= index < len(self.evaluations):
            # 编辑模式：保持原有的 ID 和创建时间
            ev['id'] = self.evaluations[index]['id']
            ev['created_at'] = self.evaluations[index].get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            ev['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.evaluations[index] = ev
        else:
            # 新增模式
            ev['id'] = len(self.evaluations) + 1
            ev['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.evaluations.append(ev)
        
        self._save_evaluations()
        return ev

    def add_evaluation(self, ev):
        ev['id'] = len(self.evaluations) + 1
        ev['created_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.evaluations.append(ev)
        self._save_evaluations()
        return ev

# ==================== 初始化 ====================
db = DataStore()

# ===================== 核心函数（修复后） =====================
def generate_pdf(evaluation):
    """
    生成评估报告PDF
    :param evaluation: 评估记录字典
    :return: BytesIO 二进制PDF流
    """
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()

        # 定义中文字体样式（修复颜色定义错误）
        chinese_styles = {
            'Heading1': ParagraphStyle(
                'CustomHeading1', parent=styles['Heading1'], fontName=CHINESE_FONT,
                fontSize=18, spaceAfter=20, alignment=1
            ),
            'Heading2': ParagraphStyle(
                'CustomHeading2', parent=styles['Heading2'], fontName=CHINESE_FONT,
                fontSize=14, spaceAfter=12
            ),
            'Normal': ParagraphStyle(
                'CustomNormal', parent=styles['Normal'], fontName=CHINESE_FONT,
                fontSize=12, spaceAfter=6
            ),
            'TotalScore': ParagraphStyle(
                'CustomTotalScore', parent=styles['Normal'], fontName=CHINESE_FONT,
                fontSize=16, spaceAfter=12, textColor=red, bold=True
            ),
            'KeyProcess': ParagraphStyle(
                'CustomKeyProcess', parent=styles['Normal'], fontName=CHINESE_FONT,
                fontSize=12, spaceAfter=6, textColor=HexColor('#FF8C00')  # 修复颜色定义
            )
        }

        elements = []
        elements.append(Paragraph("工厂流程审核报告", chinese_styles['Heading1']))
        
        # 安全获取工厂名称（修复StopIteration异常）
        factory_name = "未知工厂"
        try:
            factory_name = next(f['name'] for f in db.factories if f['id'] == evaluation['factory_id'])
        except StopIteration:
            print(f"警告：未找到工厂ID为 {evaluation['factory_id']} 的工厂")

        # 构建基础信息（增加空值安全处理）
        elements.extend([
            Paragraph(f"工厂名称：{factory_name}", chinese_styles['Normal']),
            Paragraph(f"评估日期：{evaluation.get('eval_date', '未记录')}", chinese_styles['Normal']),
            Paragraph(f"评估人员：{evaluation.get('evaluator', '未记录')}", chinese_styles['Normal']),
            Paragraph(f"审核性质：{evaluation.get('eval_type', '未记录')}", chinese_styles['Normal']),
            # 安全处理总分（避免KeyError/TypeError）
            Paragraph(f"工厂总分：{evaluation.get('overall_percent', 0):.2f}%", chinese_styles['TotalScore']),
            Spacer(1, 12)
        ])

        # 存在问题汇总
        elements.append(Paragraph("一、存在问题汇总", chinese_styles['Heading2']))
        elements.append(Paragraph("经评估，请该工厂注意以下方面：", chinese_styles['Normal']))

        key_items = []
        other_items = []

        # 遍历评估模块（修复缩进错误+增加安全检查）
        for mod_name in evaluation.get('selected_modules', []):
            # 安全检查：模块是否存在
            if mod_name not in db.modules:
                print(f"Warning: Module {mod_name} not found in current configuration.")
                continue
            
            mod = db.modules[mod_name]
            # 安全遍历子模块
            for sub_name, sub_mod in mod.get('sub_modules', {}).items():
                # 安全遍历评估项
                for item in sub_mod.get('items', []):
                    res = evaluation.get('results', {}).get(item['id'], {})
                    if not res.get('is_checked', False):
                        item_text = f"【{mod_name}-{sub_name}】{item.get('name', '未知项')}"
                        if res.get('details'):
                            item_text += f"（问题详情：{', '.join(res['details'])}）"
                        if item.get('comment'):
                            item_text += f" 改进建议：{item['comment']}"

                        if item.get('is_key', False):
                            key_items.append(item_text)
                        else:
                            other_items.append(item_text)

        # 重点工序
        if key_items:
            elements.append(Paragraph("（一）重点工序", chinese_styles['KeyProcess']))
            for i, text in enumerate(key_items, 1):
                elements.append(Paragraph(f"{i}. {text}", chinese_styles['KeyProcess']))
                elements.append(Spacer(1, 6))
        else:
            elements.append(Paragraph("（一）重点工序：本次评估未发现重点工序问题", chinese_styles['KeyProcess']))
            elements.append(Spacer(1, 6))

        # 其他工序
        if other_items:
            elements.append(Paragraph("（二）其他工序", chinese_styles['Normal']))
            for i, text in enumerate(other_items, 1):
                elements.append(Paragraph(f"{i}. {text}", chinese_styles['Normal']))
                elements.append(Spacer(1, 6))
        else:
            elements.append(Paragraph("（二）其他工序：本次评估未发现其他工序问题", chinese_styles['Normal']))
            elements.append(Spacer(1, 6))

        # 评估者评论
        elements.append(Paragraph("二、评估者评论", chinese_styles['Heading2']))
        if evaluation.get('comments'):
            elements.append(Paragraph(evaluation['comments'], chinese_styles['Normal']))
        else:
            elements.append(Paragraph("无评论", chinese_styles['Normal']))

        # 生成PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer
    
    except Exception as e:
        st.error(f"生成PDF失败：{str(e)}")
        print(f"PDF生成错误详情：{e}")
        return None

def handle_edit_logic(record, index):
    """
    点击编辑按钮后调用的逻辑
    :param record: 要编辑的评估记录
    :param index: 记录在列表中的索引
    """
    try:
        # 将记录存入 session 状态，供评估表单读取
        st.session_state.editing_record = record
        st.session_state.editing_index = index
        st.session_state.is_edit_mode = True
        
        # 强制切换回“开始评估”页面
        st.session_state.menu_choice = "🏠 开始评估" 
        st.rerun()
    except Exception as e:
        st.error(f"进入编辑模式失败：{str(e)}")

def get_default_val(key, default=False):
    """
    安全获取回填值：如果是编辑模式，取历史值；否则取默认值
    :param key: 评估项ID
    :param default: 默认值
    :return: 回填值/默认值
    """
    try:
        if st.session_state.get("is_edit_mode") and st.session_state.get("editing_record"):
            return st.session_state.editing_record.get("results", {}).get(key, default)
        return default
    except Exception as e:
        print(f"获取默认值失败：{e}")
        return default

def inject_print_css():
    """注入打印优化样式"""
    st.markdown("""
        <style>
        @media print {
            /* 隐藏侧边栏、顶部导航、按钮、工具栏 */
            [data-testid="stSidebar"], 
            header, 
            footer, 
            .stButton, 
            [data-testid="stToolbar"],
            .stTabs {
                display: none !important;
            }
            /* 扩展正文宽度到整张纸 */
            .main .block-container {
                max-width: 100% !important;
                padding: 1cm !important;
            }
            /* 强制显示复选框的边框（部分浏览器默认不打印背景） */
            input[type="checkbox"] {
                -webkit-print-color-adjust: exact;
            }
        }
        </style>
    """, unsafe_allow_html=True)

def save_evaluation_logic(new_record):
    """
    核心保存逻辑：区分『新增』与『覆盖』
    :param new_record: 新的/编辑后的评估记录
    """
    try:
        # 获取当前所有评估记录
        all_evals = db.evaluations 
        
        if st.session_state.get("is_edit_mode"):
            # --- 覆盖模式 ---
            edit_idx = st.session_state.get("editing_index")
            
            # 安全检查：确保索引有效
            if edit_idx is not None and 0 <= edit_idx < len(all_evals):
                # 1. 替换旧记录
                all_evals[edit_idx] = new_record
                
                # 2. 持久化到 JSON 或 服务器
                db.save_evaluations() 
                
                st.success(f"✅ 报告已成功更新！(记录索引: {edit_idx})")
                
                # 3. 退出编辑模式并重置状态
                st.session_state.is_edit_mode = False
                st.session_state.editing_record = None
                st.session_state.editing_index = None
                
                # 4. 延迟刷新，让用户看清成功提示
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ 编辑失败：找不到原始记录索引。")
        else:
            # --- 正常新增模式 ---
            all_evals.append(new_record)
            db.save_evaluations()
            st.success("✅ 新评估报告已保存！")
            st.rerun()
    except Exception as e:
        st.error(f"保存评估记录失败：{str(e)}")
        print(f"保存逻辑错误详情：{e}")
        
# def generate_pdf(evaluation):
#     buffer = BytesIO()
#     doc = SimpleDocTemplate(buffer, pagesize=A4)
#     styles = getSampleStyleSheet()

#     chinese_styles = {
#         'Heading1': ParagraphStyle(
#             'CustomHeading1', parent=styles['Heading1'], fontName=CHINESE_FONT,
#             fontSize=18, spaceAfter=20, alignment=1
#         ),
#         'Heading2': ParagraphStyle(
#             'CustomHeading2', parent=styles['Heading2'], fontName=CHINESE_FONT,
#             fontSize=14, spaceAfter=12
#         ),
#         'Normal': ParagraphStyle(
#             'CustomNormal', parent=styles['Normal'], fontName=CHINESE_FONT,
#             fontSize=12, spaceAfter=6
#         ),
#         'TotalScore': ParagraphStyle(
#             'CustomTotalScore', parent=styles['Normal'], fontName=CHINESE_FONT,
#             fontSize=16, spaceAfter=12, textColor='red', bold=True
#         ),
#         'KeyProcess': ParagraphStyle(
#             'CustomKeyProcess', parent=styles['Normal'], fontName=CHINESE_FONT,
#             fontSize=12, spaceAfter=6, textColor='#FF8C00'
#         )
#     }

#     elements = []
#     elements.append(Paragraph("工厂流程审核报告", chinese_styles['Heading1']))
#     factory_name = next(f['name'] for f in db.factories if f['id'] == evaluation['factory_id'])
#     elements.extend([
#         Paragraph(f"工厂名称：{factory_name}", chinese_styles['Normal']),
#         Paragraph(f"评估日期：{evaluation['eval_date']}", chinese_styles['Normal']),
#         Paragraph(f"评估人员：{evaluation['evaluator']}", chinese_styles['Normal']),
#         Paragraph(f"审核性质：{evaluation.get('eval_type', '未记录')}", chinese_styles['Normal']), # 新增行
#         Paragraph(f"工厂总分：{evaluation['overall_percent']:.2f}%", chinese_styles['TotalScore']),
#         Spacer(1, 12)
#     ])

#     elements.append(Paragraph("一、存在问题汇总", chinese_styles['Heading2']))
#     elements.append(Paragraph("经评估，请该工厂注意以下方面：", chinese_styles['Normal']))

#     key_items = []
#     other_items = []

#     for mod_name in evaluation['selected_modules']:
#             # --- 修改点：增加安全检查 ---
#         if mod_name not in db.modules:
#             # 如果历史记录中的模块名在当前配置里找不到了，跳过此模块或打印日志
#             print(f"Warning: Module {mod_name} not found in current configuration.")
#             continue
#         mod = db.modules[mod_name]
#         for sub_name, sub_mod in mod['sub_modules'].items():
#             for item in sub_mod['items']:
#                 res = evaluation['results'].get(item['id'], {})
#                 if not res.get('is_checked', False):
#                     item_text = f"【{mod_name}-{sub_name}】{item['name']}"
#                     if res.get('details'):
#                         item_text += f"（问题详情：{', '.join(res['details'])}）"
#                     if item['comment']:
#                         item_text += f" 改进建议：{item['comment']}"

#                     if item.get('is_key', False):
#                         key_items.append(item_text)
#                     else:
#                         other_items.append(item_text)

#     if key_items:
#         elements.append(Paragraph("（一）重点工序", chinese_styles['KeyProcess']))
#         for i, text in enumerate(key_items, 1):
#             elements.append(Paragraph(f"{i}. {text}", chinese_styles['KeyProcess']))
#             elements.append(Spacer(1, 6))
#     else:
#         elements.append(Paragraph("（一）重点工序：本次评估未发现重点工序问题", chinese_styles['KeyProcess']))
#         elements.append(Spacer(1, 6))

#     if other_items:
#         elements.append(Paragraph("（二）其他工序", chinese_styles['Normal']))
#         for i, text in enumerate(other_items, 1):
#             elements.append(Paragraph(f"{i}. {text}", chinese_styles['Normal']))
#             elements.append(Spacer(1, 6))
#     else:
#         elements.append(Paragraph("（二）其他工序：本次评估未发现其他工序问题", chinese_styles['Normal']))
#         elements.append(Spacer(1, 6))

#     elements.append(Paragraph("二、评估者评论", chinese_styles['Heading2']))
#     if evaluation['comments']:
#         elements.append(Paragraph(evaluation['comments'], chinese_styles['Normal']))
#     else:
#         elements.append(Paragraph("无评论", chinese_styles['Normal']))

#     doc.build(elements)
#     buffer.seek(0)
#     return buffer

# def handle_edit_logic(record, index):
#     """
#     点击编辑按钮后调用的逻辑
#     """
#     # 将记录存入 session 状态，供评估表单读取
#     st.session_state.editing_record = record
#     st.session_state.editing_index = index
#     st.session_state.is_edit_mode = True
    
#     # 强制切换回“开始评估”页面
#     # 注意：这里的字符串要和你 sidebar.radio 里的“开始评估”选项完全一致
#     st.session_state.menu_choice = "🏠 开始评估" 
#     st.rerun()

# def get_default_val(key, default=False):
#     """
#     安全获取回填值：如果是编辑模式，取历史值；否则取默认值
#     """
#     if st.session_state.get("is_edit_mode") and st.session_state.get("editing_record"):
#         return st.session_state.editing_record.get("results", {}).get(key, default)
#     return default

# def inject_print_css():
#     """
#     注入打印优化样式
#     """
#     st.markdown("""
#         <style>
#         @media print {
#             /* 隐藏侧边栏、顶部导航、按钮、工具栏 */
#             [data-testid="stSidebar"], 
#             header, 
#             footer, 
#             .stButton, 
#             [data-testid="stToolbar"],
#             .stTabs {
#                 display: none !important;
#             }
#             /* 扩展正文宽度到整张纸 */
#             .main .block-container {
#                 max-width: 100% !important;
#                 padding: 1cm !important;
#             }
#             /* 强制显示复选框的边框（部分浏览器默认不打印背景） */
#             input[type="checkbox"] {
#                 -webkit-print-color-adjust: exact;
#             }
#         }
#         </style>
#     """, unsafe_allow_html=True)

# def save_evaluation_logic(new_record):
#     """
#     核心保存逻辑：区分『新增』与『覆盖』
#     """
#     # 获取当前所有评估记录
#     all_evals = db.evaluations 
    
#     if st.session_state.get("is_edit_mode"):
#         # --- 覆盖模式 ---
#         edit_idx = st.session_state.get("editing_index")
        
#         # 安全检查：确保索引有效
#         if edit_idx is not None and 0 <= edit_idx < len(all_evals):
#             # 1. 替换旧记录
#             all_evals[edit_idx] = new_record
            
#             # 2. 持久化到 JSON 或 服务器
#             db.save_evaluations() 
            
#             st.success(f"✅ 报告已成功更新！(记录索引: {edit_idx})")
            
#             # 3. 退出编辑模式并重置状态
#             st.session_state.is_edit_mode = False
#             st.session_state.editing_record = None
#             st.session_state.editing_index = None
            
#             # 4. 延迟刷新，让用户看清成功提示
#             import time
#             time.sleep(1)
#             st.rerun()
#         else:
#             st.error("❌ 编辑失败：找不到原始记录索引。")
#     else:
#         # --- 正常新增模式 ---
#         all_evals.append(new_record)
#         db.save_evaluations()
#         st.success("✅ 新评估报告已保存！")
#         st.rerun()

# ==================== 页面路由 ====================
def main():
    if 'user' not in st.session_state:
        st.title("欧图工厂生产流程审核系统")
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            if st.button("登录", type="primary"):
                if next((u for u in db.users if u['username'] == username and u['password'] == password), None):
                    st.session_state['user'] = username
                    st.rerun()
                else:
                    st.error("账号或密码错误")
        return

    st.sidebar.title(f"欢迎，{st.session_state['user']}")
    if st.sidebar.button("退出登录"):
        del st.session_state['user']
        if 'eval_results' in st.session_state:
            del st.session_state['eval_results']
        st.rerun()

    menu = st.sidebar.radio("功能菜单", ["开始评估", "历史记录", "数据分析"])

    if menu == "开始评估":
        start_evaluation()
    elif menu == "历史记录":
        show_history()
    elif menu == "数据分析":
        show_data_analysis()

# ==================== 核心评估页面（一键全选/清空 修复版） ====================
def start_evaluation(current_user_id):
    inject_custom_css()
    inject_print_css()
    st.subheader("欢迎回来，评估员")
    
    # 编辑模式提醒
    if st.session_state.get("is_edit_mode"):
        st.warning(f"🔄 正在编辑历史记录：{st.session_state.editing_record.get('eval_date', '未知日期')}")
        if st.button("取消编辑"):
            st.session_state.is_edit_mode = False
            st.session_state.editing_record = None
            st.rerun()

    # 定义系统固定总分分母
    SYSTEM_TOTAL_FIXED = 177

    # --- 1. 基础配置 ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        # 回填工厂 ID
        default_fty = get_default_val("factory_id", db.factories[0]['id'] if db.factories else "")
        # 找到对应 ID 在列表中的索引
        fty_options = [(f['id'], f['name']) for f in db.factories] if db.factories else []
        fty_index = next((i for i, f in enumerate(fty_options) if f[0] == default_fty), 0)
        factory_id = st.selectbox("评估工厂", fty_options, index=fty_index, format_func=lambda x: x[1], key="factory_sel")[0] if fty_options else ""
    with col2:
        # 回填日期
        default_date = get_default_val("eval_date", date.today())
        if isinstance(default_date, str): # 如果从 JSON 读取的是字符串则转换
             default_date = datetime.strptime(default_date, "%Y-%m-%d").date()
        eval_date = st.date_input("评估日期", default_date, key="date_sel")
    with col3:
        evaluator = st.text_input("评估员", value=st.session_state.get('user', ''), key="evaluator_sel")
    with col4:
        eval_type = st.selectbox("审核性质", ["常规审核", "整改复查"], key="eval_type_sel")

    # 整改复查对比逻辑
    last_ev = None
    if eval_type == "整改复查" and factory_id:
        past_evals = [e for e in db.evaluations if e.get('factory_id') == factory_id] if hasattr(db, 'evaluations') else []
        if past_evals:
            last_ev = sorted(past_evals, key=lambda x: x.get('eval_date', ''), reverse=True)[0]
        else:
            st.info("该工厂暂无历史评估记录，将以常规模式进行。")

    all_modules = list(db.modules.keys()) if hasattr(db, 'modules') else []
    selected_modules = all_modules if eval_type == "常规审核" else st.multiselect("选择复查模块", all_modules, key="modules_sel")
    
    if not selected_modules:
        st.info("请选择上方模块开始评分")
        return

    # --- 2. 状态初始化 & 提取所有 ID ---
    if 'eval_results' not in st.session_state:
        st.session_state.eval_results = {}
    
    # 修复点：定义 all_item_ids 用于全选功能
    all_item_ids = []
    for mod_name in selected_modules:
        mod_data = db.modules.get(mod_name, {})
        for sub_mod in mod_data.get('sub_modules', {}).values():
            for it in sub_mod.get('items', []):
                it_id = it['id']
                all_item_ids.append(it_id) # 收集所有 ID
                if it_id not in st.session_state.eval_results:
                    st.session_state.eval_results[it_id] = {"is_checked": False, "details": [], "image_path": None}

    # --- 3. 核心评分循环（及右上角操作按钮） ---
    st.divider()

    # 使用容器布局，将按钮精准定位在分割线下方、列表右上角
    col_space, col_btns = st.columns([8.5, 1.5])
    
    with col_btns:
        # 增加一小段负边距 CSS，让按钮稍微上移，贴近分割线
        st.markdown("""
            <style>
            .st-key-small_btns_container {
                margin-top: -45px; 
            }
            div[data-testid="stColumn"] button {
                padding: 1px 2px !important;
                font-size: 11px !important;
                height: 22px !important;
                min-height: 22px !important;
                line-height: 1 !important;
                background-color: #f0f2f6;
            }
            </style>
        """, unsafe_allow_html=True)
        
        # 使用容器包裹按钮以便精确定位
        with st.container():
            sub_c1, sub_c2 = st.columns(2)
            if sub_c1.button("全选", key="small_all"):
                for it_id in all_item_ids:
                    st.session_state[f"chk_{it_id}"] = True
                    st.session_state.eval_results[it_id]["is_checked"] = True
                st.rerun()
            if sub_c2.button("清空", key="small_none"):
                for it_id in all_item_ids:
                    st.session_state[f"chk_{it_id}"] = False
                    st.session_state.eval_results[it_id]["is_checked"] = False
                st.rerun()

    total_system_earned = 0
    # 核心评分循环
    for mod_name in selected_modules:
        mod_data = db.modules.get(mod_name, {})
        
        # 计算该模块实时总分
        mod_earned = 0
        for sub in mod_data.get('sub_modules', {}).values():
            mod_earned += sum(it.get('score', 0) for it in sub.get('items', []) if st.session_state.get(f"chk_{it['id']}", False))
        
        # 换算百分比 (基于177)
        mod_score_percent = (mod_earned / SYSTEM_TOTAL_FIXED * 100) if SYSTEM_TOTAL_FIXED != 0 else 0
        total_system_earned += mod_earned

        # 计算上一次模块得分
        last_mod_info = ""
        if last_ev:
            last_mod_earned = 0
            for s_name, s_data in mod_data.get('sub_modules', {}).items():
                last_mod_earned += sum(it.get('score', 0) for it in s_data.get('items', []) if last_ev.get('results', {}).get(it['id'], {}).get('is_checked', False))
            last_mod_percent = (last_mod_earned / SYSTEM_TOTAL_FIXED * 100) if SYSTEM_TOTAL_FIXED != 0 else 0
            last_mod_info = f" (上次: {last_mod_percent:.1f}%)"

        with st.expander(f"📦{mod_name}", expanded=True):
            st.write(f"**模块得分: :blue[{mod_score_percent:.1f}%]** {last_mod_info}")
            
            for sub_name, sub_mod in mod_data.get('sub_modules', {}).items():
                sub_earned = sum(it.get('score', 0) for it in sub_mod.get('items', []) if st.session_state.get(f"chk_{it['id']}", False))
                sub_score_percent = (sub_earned / SYSTEM_TOTAL_FIXED * 100) if SYSTEM_TOTAL_FIXED != 0 else 0

                # 计算上一次子项得分
                last_sub_info = ""
                if last_ev:
                    last_sub_earned = sum(it.get('score', 0) for it in sub_mod.get('items', []) if last_ev.get('results', {}).get(it['id'], {}).get('is_checked', False))
                    last_sub_percent = (last_sub_earned / SYSTEM_TOTAL_FIXED * 100) if SYSTEM_TOTAL_FIXED != 0 else 0
                    last_sub_info = f" (上次: {last_sub_percent:.1f}%)"

                sub_key = f"exp_{factory_id}_{mod_name}_{sub_name}"
                with st.expander(f"🔹 {sub_name}", expanded=True, key=sub_key):
                    st.write(f"**子项得分: :green[{sub_score_percent:.1f}%]** {last_sub_info}")
                    st.write("") 

                    for it in sub_mod.get('items', []):
                        it_id = it['id']
                        c1, c2, c3 = st.columns([0.65, 0.2, 0.15])
                        
                        # 计算上一次该项是否合格
                        last_item_status = ""
                        if last_ev:
                            was_ok = last_ev.get('results', {}).get(it_id, {}).get('is_checked', False)
                            last_item_status = " | :green[上次合格]" if was_ok else " | :red[上次不合格]"

                        with c1:
                            label = f":orange[{it['name']} (关键项)]" if it.get('is_key') else it['name']
                            full_label = f"{label}{last_item_status}"
                            
                            # 回填复选框
                            history_results = st.session_state.get("editing_record", {}).get("results", {})
                            history_item_checked = history_results.get(it_id, {}).get('is_checked', False)
                            
                            # 使用 get_default_val 的逻辑决定初始状态
                            is_checked = st.checkbox(
                                full_label, 
                                key=f"chk_{it_id}", 
                                value=history_item_checked if st.session_state.get("is_edit_mode") else st.session_state.get(f"chk_{it_id}", False)
                            )
                            st.session_state.eval_results[it_id]['is_checked'] = is_checked
                            
                        with c2:
                            with st.popover("📸 拍照上传"):
                                img_file = st.file_uploader("拍照", type=['jpg','png','jpeg'], key=f"up_{it_id}", label_visibility="collapsed")
                                if img_file:
                                    file_ext = img_file.name.split('.')[-1]
                                    file_name = f"{it_id}_{datetime.now().strftime('%H%M%S')}.{file_ext}"
                                    save_path = os.path.join(MEDIA_DIR, file_name)
                                    with open(save_path, "wb") as f:
                                        f.write(img_file.getbuffer())
                                    st.session_state.eval_results[it_id]['image_path'] = save_path
                                    st.rerun()

                        with c3:
                            img_path = st.session_state.eval_results[it_id].get('image_path')
                            if img_path and os.path.exists(img_path):
                                st.image(img_path, width=40)
                                sc1, sc2 = st.columns(2)
                                with sc1:
                                    if st.button("👁️", key=f"v_{it_id}"): show_full_image(img_path)
                                with sc2:
                                    if st.button("🗑️", key=f"d_{it_id}"):
                                        if os.path.exists(img_path): os.remove(img_path)
                                        st.session_state.eval_results[it_id]['image_path'] = None
                                        st.rerun()

                        if not is_checked:
                            if it.get('details'):
                                st.session_state.eval_results[it_id]['details'] = st.multiselect(
                                    "缺陷选择", it['details'],
                                    default=st.session_state.eval_results[it_id]['details'],
                                    key=f"det_{it_id}", label_visibility="collapsed"
                                )
                            if it.get('comment'):
                                st.caption(f"💡 建议：{it['comment']}")
                        st.divider()

    # --- 5. 总结区 ---
    st.subheader("评估汇总")
    overall_percent = (total_system_earned / SYSTEM_TOTAL_FIXED * 100) if SYSTEM_TOTAL_FIXED != 0 else 0
    
    if last_ev:
        last_overall = last_ev.get('overall_percent', 0)
        st.metric("总得分率", f"{overall_percent:.2f}%", delta=f"{overall_percent - last_overall:.2f}%")
    else:
        st.metric("总得分率", f"{overall_percent:.2f}%")
        
    comments = st.text_area("综合评估意见", height=80, key="comments_sel")

    # --- 保存逻辑（核心修复区） ---
    if st.button("保存并生成报告", type="primary"):
        # 组装评估数据
        ev_data = {
            "factory_id": factory_id,
            "evaluator": evaluator,
            "eval_date": eval_date.strftime("%Y-%m-%d"),  # 确保是字符串
            "evaluator_id": current_user_id,  # 用传入的current_user_id，而非session_state
            "eval_type": eval_type,
            "selected_modules": selected_modules,
            "overall_percent": overall_percent,
            "results": st.session_state.eval_results,
            "comments": comments
        }
        
        # 调用保存逻辑
        save_evaluation_logic(ev_data)
        
        # ========== 核心修复：用ev_data替代未定义的saved_record ==========
        try:
            # 生成PDF（使用组装好的ev_data）
            pdf_buf = generate_pdf(ev_data) 
            if pdf_buf:
                # 修复文件名：用factory_id替代不存在的id，日期转字符串
                file_name = f"工厂评估报告_{factory_id}_{eval_date.strftime('%Y-%m-%d')}.pdf"
                st.download_button(
                    label="📥 下载评估报告 (PDF)",
                    data=pdf_buf,
                    file_name=file_name,
                    mime="application/pdf",
                    key="pdf_download"
                )
            else:
                st.warning("PDF生成失败，无法下载")
        except Exception as e:
            st.error(f"生成PDF失败：{str(e)}")
        
        # 重置评估结果状态（可选，避免下次评估带旧数据）
        st.session_state.eval_results = {}
# ==================== 核心评估页面（优化版：拍照/缩略图/大图） ====================
# def start_evaluation(current_user_id):
#     inject_custom_css()
#     inject_print_css()  # <--- 【添加位置 1】
#     st.subheader("欢迎回来，评估员")
    
#     # 【新增：编辑模式提醒】
#     if st.session_state.get("is_edit_mode"):
#         st.warning(f"🔄 正在编辑历史记录：{st.session_state.editing_record.get('eval_date')}")
#         if st.button("取消编辑"):
#             st.session_state.is_edit_mode = False
#             st.session_state.editing_record = None
#             st.rerun()

#     # 定义系统固定总分分母
#     SYSTEM_TOTAL_FIXED = 177

#    # --- 1. 基础配置 ---
#     col1, col2, col3, col4 = st.columns(4)
#     with col1:
#         # 回填工厂 ID
#         default_fty = get_default_val("factory_id", db.factories[0]['id'])
#         # 找到对应 ID 在列表中的索引
#         fty_options = [(f['id'], f['name']) for f in db.factories]
#         fty_index = next((i for i, f in enumerate(fty_options) if f[0] == default_fty), 0)
#         factory_id = st.selectbox("评估工厂", fty_options, index=fty_index, format_func=lambda x: x[1])[0]
#     with col2:
#         # 回填日期
#         default_date = get_default_val("eval_date", date.today())
#         if isinstance(default_date, str): # 如果从 JSON 读取的是字符串则转换
#              default_date = datetime.strptime(default_date, "%Y-%m-%d").date()
#         eval_date = st.date_input("评估日期", default_date)
#     with col3:
#         evaluator = st.text_input("评估员", value=st.session_state.get('user', ''))
#     with col4:
#         eval_type = st.selectbox("审核性质", ["常规审核", "整改复查"])

#     # 【新增功能：整改复查对比逻辑】
#     last_ev = None
#     if eval_type == "整改复查":
#         past_evals = [e for e in db.evaluations if e['factory_id'] == factory_id]
#         if past_evals:
#             last_ev = sorted(past_evals, key=lambda x: x['eval_date'], reverse=True)[0]
#         else:
#             st.info("该工厂暂无历史评估记录，将以常规模式进行。")

#     all_modules = list(db.modules.keys())
#     selected_modules = all_modules if eval_type == "常规审核" else st.multiselect("选择复查模块", all_modules)
    
#     if not selected_modules:
#         st.info("请选择上方模块开始评分")
#         return

#     # --- 2. 状态初始化 & 提取所有 ID ---
#     if 'eval_results' not in st.session_state:
#         st.session_state.eval_results = {}
    
#     # 修复点：定义 all_item_ids 用于全选功能
#     all_item_ids = []
#     for mod_name in selected_modules:
#         for sub_mod in db.modules[mod_name]['sub_modules'].values():
#             for it in sub_mod['items']:
#                 it_id = it['id']
#                 all_item_ids.append(it_id) # 收集所有 ID
#                 if it_id not in st.session_state.eval_results:
#                     st.session_state.eval_results[it_id] = {"is_checked": False, "details": [], "image_path": None}

#    # --- 3. 核心评分循环（及右上角操作按钮） ---
#     st.divider()

#     # 使用容器布局，将按钮精准定位在分割线下方、列表右上角
#     # col_space 占比 8.5，确保按钮被推到最右
#     col_space, col_btns = st.columns([8.5, 1.5])
    
#     with col_btns:
#         # 增加一小段负边距 CSS，让按钮稍微上移，贴近分割线
#         st.markdown("""
#             <style>
#             .st-key-small_btns_container {
#                 margin-top: -45px; 
#             }
#             div[data-testid="stColumn"] button {
#                 padding: 1px 2px !important;
#                 font-size: 11px !important;
#                 height: 22px !important;
#                 min-height: 22px !important;
#                 line-height: 1 !important;
#                 background-color: #f0f2f6;
#             }
#             </style>
#         """, unsafe_allow_html=True)
        
#         # 使用容器包裹按钮以便精确定位
#         with st.container():
#             sub_c1, sub_c2 = st.columns(2)
#             if sub_c1.button("全选", key="small_all"):
#                 for it_id in all_item_ids:
#                     st.session_state[f"chk_{it_id}"] = True
#                     st.session_state.eval_results[it_id]["is_checked"] = True
#                 st.rerun()
#             if sub_c2.button("清空", key="small_none"):
#                 for it_id in all_item_ids:
#                     st.session_state[f"chk_{it_id}"] = False
#                     st.session_state.eval_results[it_id]["is_checked"] = False
#                 st.rerun()

#     total_system_earned = 0
#     # ... 后面接原来的 for mod_name in selected_modules: ...

#     for mod_name in selected_modules:
#         mod_data = db.modules[mod_name]
        
#         # 计算该模块实时总分
#         mod_earned = 0
#         for sub in mod_data['sub_modules'].values():
#             mod_earned += sum(it['score'] for it in sub['items'] if st.session_state.get(f"chk_{it['id']}", False))
        
#         # 换算百分比 (基于177)
#         mod_score_percent = (mod_earned / SYSTEM_TOTAL_FIXED * 100)
#         total_system_earned += mod_earned

#         # 【计算上一次模块得分】
#         last_mod_info = ""
#         if last_ev:
#             last_mod_earned = 0
#             for s_name, s_data in mod_data['sub_modules'].items():
#                 last_mod_earned += sum(it['score'] for it in s_data['items'] if last_ev['results'].get(it['id'], {}).get('is_checked', False))
#             last_mod_percent = (last_mod_earned / SYSTEM_TOTAL_FIXED * 100)
#             last_mod_info = f" (上次: {last_mod_percent:.1f}%)"

#         with st.expander(f"📦{mod_name}", expanded=True):
#             st.write(f"**模块得分: :blue[{mod_score_percent:.1f}%]** {last_mod_info}")
            
#             for sub_name, sub_mod in mod_data['sub_modules'].items():
#                 sub_earned = sum(it['score'] for it in sub_mod['items'] if st.session_state.get(f"chk_{it['id']}", False))
#                 sub_score_percent = (sub_earned / SYSTEM_TOTAL_FIXED * 100)

#                 # 【计算上一次子项得分】
#                 last_sub_info = ""
#                 if last_ev:
#                     last_sub_earned = sum(it['score'] for it in sub_mod['items'] if last_ev['results'].get(it['id'], {}).get('is_checked', False))
#                     last_sub_percent = (last_sub_earned / SYSTEM_TOTAL_FIXED * 100)
#                     last_sub_info = f" (上次: {last_sub_percent:.1f}%)"

#                 sub_key = f"exp_{factory_id}_{mod_name}_{sub_name}"
#                 with st.expander(f"🔹 {sub_name}", expanded=True, key=sub_key):
#                     st.write(f"**子项得分: :green[{sub_score_percent:.1f}%]** {last_sub_info}")
#                     st.write("") 

#                     for it in sub_mod['items']:
#                         it_id = it['id']
#                         c1, c2, c3 = st.columns([0.65, 0.2, 0.15])
                        
#                         # 【计算上一次该项是否合格】
#                         last_item_status = ""
#                         if last_ev:
#                             was_ok = last_ev['results'].get(it_id, {}).get('is_checked', False)
#                             last_item_status = " | :green[上次合格]" if was_ok else " | :red[上次不合格]"

#                        # ... 在循环内部 ...
#                         with c1:
#                             label = f":orange[{it['name']} (关键项)]" if it.get('is_key') else it['name']
#                             full_label = f"{label}{last_item_status}"
                            
#                             # --- 【修改位置 2：回填复选框】 ---
#                             # 关键：从历史记录的 results 字典里按 ID 找之前的 is_checked
#                             history_results = st.session_state.get("editing_record", {}).get("results", {})
#                             history_item_checked = history_results.get(it_id, {}).get("is_checked", False)
                            
#                             # 使用 get_default_val 的逻辑决定初始状态
#                             is_checked = st.checkbox(
#                                 full_label, 
#                                 key=f"chk_{it_id}", 
#                                 value=history_item_checked if st.session_state.get("is_edit_mode") else st.session_state.get(f"chk_{it_id}", False)
#                             )
#                             st.session_state.eval_results[it_id]['is_checked'] = is_checked
                            
#                         with c2:
#                             with st.popover("📸 拍照上传"):
#                                 img_file = st.file_uploader("拍照", type=['jpg','png','jpeg'], key=f"up_{it_id}", label_visibility="collapsed")
#                                 if img_file:
#                                     file_ext = img_file.name.split('.')[-1]
#                                     file_name = f"{it_id}_{datetime.now().strftime('%H%M%S')}.{file_ext}"
#                                     save_path = os.path.join(MEDIA_DIR, file_name)
#                                     with open(save_path, "wb") as f:
#                                         f.write(img_file.getbuffer())
#                                     st.session_state.eval_results[it_id]['image_path'] = save_path
#                                     st.rerun()

#                         with c3:
#                             img_path = st.session_state.eval_results[it_id].get('image_path')
#                             if img_path and os.path.exists(img_path):
#                                 st.image(img_path, width=40)
#                                 sc1, sc2 = st.columns(2)
#                                 with sc1:
#                                     if st.button("👁️", key=f"v_{it_id}"): show_full_image(img_path)
#                                 with sc2:
#                                     if st.button("🗑️", key=f"d_{it_id}"):
#                                         if os.path.exists(img_path): os.remove(img_path)
#                                         st.session_state.eval_results[it_id]['image_path'] = None
#                                         st.rerun()

#                         if not is_checked:
#                             if it['details']:
#                                 st.session_state.eval_results[it_id]['details'] = st.multiselect(
#                                     "缺陷选择", it['details'],
#                                     default=st.session_state.eval_results[it_id]['details'],
#                                     key=f"det_{it_id}", label_visibility="collapsed"
#                                 )
#                             if it['comment']:
#                                 st.caption(f"💡 建议：{it['comment']}")
#                         st.divider()

#     # --- 5. 总结区 ---
#     st.subheader("评估汇总")
#     overall_percent = (total_system_earned / SYSTEM_TOTAL_FIXED * 100)
    
#     if last_ev:
#         st.metric("总得分率", f"{overall_percent:.2f}%", delta=f"{overall_percent - last_ev['overall_percent']:.2f}%")
#     else:
#         st.metric("总得分率", f"{overall_percent:.2f}%")
        
#     comments = st.text_area("综合评估意见", height=80)

#     # --- 【修改位置 3：保存逻辑】 ---
#     if st.button("保存并生成报告", type="primary"):
#         ev_data = {
#             "factory_id": factory_id,
#             "evaluator": evaluator,
#             "eval_date": eval_date.strftime("%Y-%m-%d"),
#             "evaluator_id": st.session_state.user_id,
#             "eval_type": eval_type,
#             "selected_modules": selected_modules,
#             "overall_percent": overall_percent,
#             "results": st.session_state.eval_results,
#             "comments": comments
#         }
        
#         # 调用覆盖逻辑函数
#         save_evaluation_logic(ev_data)
        
#         pdf_buf = generate_pdf(saved_record) 
#         st.download_button(
#             label="📥 下载评估报告 (PDF)",
#             data=pdf_buf,
#             file_name=f"工厂评估报告_{saved_record['id']}_{eval_date}.pdf",
#             mime="application/pdf"
#         )

# ==================== 数据分析看板 ====================
def show_data_analysis(evals_to_show):
    st.header("📊 工厂数据深度看板")
    
    # 1. 基础数据检查
    evals = db.evaluations
    if not evals:
        st.info("💡 暂无评估记录。")
        return

    # 转换为 DataFrame
    df = pd.DataFrame(evals_to_show)
    df['eval_date'] = pd.to_datetime(df['eval_date'])
    factory_map = {f['id']: f['name'] for f in db.factories}

    # 2. 筛选器
    selected_f_id = st.selectbox("选择分析工厂", options=list(factory_map.keys()), 
                                 format_func=lambda x: factory_map[x])
    f_df = df[df['factory_id'] == selected_f_id].sort_values('eval_date')

    # --- 第一部分：工厂健康趋势图 ---
    st.subheader("📈 工厂健康趋势图")
    if not f_df.empty:
        # 创建折线图
        fig_line = px.line(
            f_df, 
            x='eval_date',           # X轴：评估日期
            y='overall_percent',     # Y轴：分数(百分比)
            title=f"{factory_map[selected_f_id]} - 质量波动趋势",
            labels={
                'overall_percent': '得分率 (%)', 
                'eval_date': '评估日期'
            },
            markers=True,            # 显示数据点
            line_shape='spline',     # 使曲线平滑
            text=f_df['overall_percent'].apply(lambda x: f"{x:.1f}%") # 在点上显示数值
        )

        # 图表样式美化
        fig_line.update_traces(
            line_color='#1f77b4', 
            line_width=3, 
            marker=dict(size=10, symbol='circle'),
            textposition="top center" # 数值显示在点上方
        )
        
        # 强制 Y 轴范围在 0-100，避免因为分数太高或太低导致坐标轴变形
        fig_line.update_yaxes(range=[0, 105])
        
        # 优化 X 轴日期显示
        fig_line.update_xaxes(
            dtick="M1", # 强制按月显示刻度
            tickformat="%Y-%m-%d" # 日期格式
        )

        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.warning("⚠️ 该工厂暂无评估记录，无法生成趋势图。")

    # --- 图表 2：模块画像雷达图 ---
    st.divider()
    st.subheader("🕸️ 模块能力画像 (最新数据)")
    if not f_df.empty:
        latest_res = f_df.iloc[-1]['results']
        r_labels, r_values = [], []
        
        for mod_name, mod_info in db.modules.items():
            mod_items = [it['id'] for sub in mod_info['sub_modules'].values() for it in sub['items']]
            earned = sum(db.get_item_score(i) for i in mod_items if latest_res.get(i,{}).get('is_checked'))
            total = sum(db.get_item_score(i) for i in mod_items)
            r_labels.append(mod_name)
            r_values.append((earned/total*100) if total > 0 else 0)

        fig_radar = go.Figure(data=go.Scatterpolar(r=r_values, theta=r_labels, fill='toself'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])))
        st.plotly_chart(fig_radar, use_container_width=True)

    # --- 图表 3：高频缺陷 Top 10 ---
    st.divider()
    st.subheader("🚨 行业高频缺陷排行 (全汇总)")
    all_details = [d for e in evals for r in e['results'].values() for d in r.get('details', [])]
    if all_details:
        top_10 = pd.Series(all_details).value_counts().head(10).reset_index()
        top_10.columns = ['缺陷描述', '频次']
        fig_bar = px.bar(top_10, x='频次', y='缺陷描述', orientation='h', color='频次')
        st.plotly_chart(fig_bar, use_container_width=True)

    # --- 表格：全小项合规穿透 ---
    st.divider()
    st.subheader("🔍 细项合规性深度穿透")
    item_analysis = []
    for m_n, m_i in db.modules.items():
        for s_n, s_i in m_i['sub_modules'].items():
            for it in s_i['items']:
                hist = [e['results'].get(it['id'],{}).get('is_checked', False) for e in evals]
                rate = (sum(hist)/len(hist)*100) if hist else 0
                item_analysis.append({"模块": m_n, "项目": it['name'], "合格率": rate})
    
    st.dataframe(pd.DataFrame(item_analysis), column_config={
        "合格率": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)
    }, use_container_width=True)
    
# ==================== 登录界面管理 ====================
def login():
    st.set_page_config(page_title="欧图工厂生产流程评估系统", layout="wide")
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🔒 欧图工厂生产流程评估系统登录")
        user_input = st.text_input("账号 (Email)")
        pwd_input = st.text_input("密码", type="password")
        
        if st.button("登录", type="primary"):
            user_info = db.verify_user(user_input, pwd_input)
            if user_info:
                st.session_state.logged_in = True
                st.session_state.user_id = user_input
                st.session_state.user_name = user_info['name']
                st.session_state.role = user_info['role']
                st.success("登录成功！")
                st.rerun()
            else:
                st.error("❌ 账号或密码不正确")
        st.stop()

def show_admin_panel():
    st.header("⚙️ 系统管理")
    
    tab1, tab2 = st.tabs(["工厂管理", "记录维护"])
    
    with tab1:
        st.subheader("编辑工厂名单")
        # 直接在网页编辑工厂 ID 和名称
        edited_factories = st.data_editor(db.factories, num_rows="dynamic", key="fty_editor")
        if st.button("保存工厂修改"):
            db.factories = edited_factories
            # 如果你有保存工厂的函数，请在这里调用，例如 db.save_factories()
            st.success("工厂列表已同步！")
            
    with tab2:
        st.subheader("全量评估记录管理")
        if not db.evaluations:
            st.info("暂无记录")
        else:
            # 将记录转为 DataFrame 显示，增加删除列
            admin_df = pd.DataFrame(db.evaluations)
            st.write("当前系统中共有", len(admin_df), "条记录")
            
            # 允许选择某一条记录进行删除
            delete_idx = st.number_input("输入要删除的记录索引 (Index)", min_value=0, max_value=len(db.evaluations)-1, step=1)
            if st.button("🗑️ 删除该条记录", type="primary"):
                target = db.evaluations[delete_idx]
                db.evaluations.pop(delete_idx)
                db.save_evaluations() # 确保存入 JSON
                st.warning(f"已删除：{target.get('eval_date')} - {target.get('evaluator_id')} 的评估")
                st.rerun()

    # with tab3:
    #     st.subheader("危险操作")
    #     if st.button("🚨 清空数据库", help="删除所有 JSON 里的评估记录"):
    #         if st.checkbox("确认清空？"):
    #             db.evaluations = []
    #             db.save_evaluations()
    #             st.success("数据已全部抹除")
    #             st.rerun()

# ==================== 历史记录 ====================
def show_history(evals_to_show):
    st.subheader("历史记录")
    if not evals_to_show:
        st.info("暂无记录")
        return
        
    # 倒序显示（最近的在前）
    for i, ev in enumerate(reversed(evals_to_show)):
        factory_name = next((f['name'] for f in db.factories if f['id'] == ev['factory_id']), "未知")
        
        with st.expander(f"📅 {ev['eval_date']} | {factory_name} | {ev['eval_type']}"):
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            with c1: st.write(f"评估人：{ev['evaluator']}")
            with c2: st.write(f"得分：{ev['overall_percent']:.2f}%")
            with c3:
                pdf_buf = generate_pdf(ev)
                st.download_button("📥 下载", pdf_buf, f"报告_{ev['id']}.pdf", key=f"dl_{ev['id']}")
            with c4:
                # --- 【修复点2】添加编辑按钮逻辑 ---
                if st.button("📝 编辑", key=f"edit_{ev['id']}"):
                    # 找到该记录在原始 db.evaluations 列表中的索引，用于后续覆盖保存
                    real_idx = -1
                    for idx, item in enumerate(db.evaluations):
                        if item['id'] == ev['id']:
                            real_idx = idx
                            break
                    
                    # 存入 session_state 并触发刷新
                    st.session_state.editing_record = ev
                    st.session_state.editing_idx = real_idx
                    st.session_state.is_edit_mode = True
                    st.rerun()
            
            st.write(f"评论：{ev['comments']}")

def main():
    # 1. 登录拦截
    login() 
    
    # 2. 侧边栏用户信息
    st.sidebar.title(f"👤 {st.session_state.user_name}")
    st.sidebar.caption(f"权限: {st.session_state.role.upper()}")
    st.sidebar.divider()
    
    # 3. 菜单定义
    menu_options = ["🏠 开始评估", "📊 数据分析", "📜 历史记录"]
    if st.session_state.role == "sadmin":
        menu_options.append("⚙️ 系统管理")
    
    # --- 【修复点1】动态确定当前页面索引 ---
    # 如果处于编辑模式，强制 index 指向“🏠 开始评估” (即 0)
    if st.session_state.get("is_edit_mode"):
        default_index = 0
    else:
        # 否则尝试恢复之前的选择，如果没有则默认为 0
        current_choice = st.session_state.get("last_menu_choice", "🏠 开始评估")
        try:
            default_index = menu_options.index(current_choice)
        except ValueError:
            default_index = 0

    # 4. 侧边栏菜单渲染
    choice = st.sidebar.radio(
        "功能导航", 
        options=menu_options,
        index=default_index,
        key="nav_radio"
    )
    
    # 记录当前选择，用于下次刷新时保持页面
    st.session_state.last_menu_choice = choice

    st.sidebar.divider()

    # 5. 获取数据
    filtered_evals = db.get_evaluations_by_user(st.session_state.user_id, st.session_state.role)

    # 6. 路由分发
    if "开始评估" in choice:
        # 传递用户ID，start_evaluation 内部需处理 st.session_state.editing_record
        start_evaluation(st.session_state.user_id) 
        
    elif "数据分析" in choice:
        st.session_state.is_edit_mode = False # 切换页面自动退出编辑态
        show_data_analysis(filtered_evals)
        
    elif "历史记录" in choice:
        st.session_state.is_edit_mode = False
        show_history(filtered_evals)
        
    elif "系统管理" in choice:
        st.session_state.is_edit_mode = False
        show_admin_panel() 

    # 7. 退出登录
    if st.sidebar.button("🚪 退出登录", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# 在程序最后运行 main
if __name__ == "__main__":
    main()
