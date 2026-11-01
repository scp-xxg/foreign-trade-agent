"""Build the one-page submission PDF. Supply a licensed TrueType Chinese font."""
import argparse
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
p=argparse.ArgumentParser();p.add_argument('--font',required=True);p.add_argument('--output',required=True);a=p.parse_args()
pdfmetrics.registerFont(TTFont('CJK',a.font))
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
body=ParagraphStyle('body',fontName='CJK',fontSize=9.5,leading=14.6,wordWrap='CJK',textColor=colors.HexColor('#243044'),spaceAfter=5)
title=ParagraphStyle('title',parent=body,fontSize=24,leading=29,textColor=colors.black,spaceAfter=7)
heading=ParagraphStyle('heading',parent=body,fontSize=12,leading=18,textColor=colors.black,spaceBefore=10,spaceAfter=5)
small=ParagraphStyle('small',parent=body,fontSize=8,leading=12)
story=[]
def text(s,style=body):story.append(Paragraph(s,style))
text('SailAgent 外贸业务协作助手',title)
text('AI＋出海参赛方案　｜　输入询盘、商品资料和企业知识，交付可核对、可修改、可下载的业务成果。')
text('目标用户与业务价值',heading)
text('面向中小外贸团队的业务员、采购跟单和商品运营，以中文对话串起 Alibaba RFQ 销售回复与 Amazon US 商品草稿。减少重复录入、报价手算及岗位间复制资料；沿用同一询盘、SKU、资料包和版本，所有未知项明确待确认。')
text('A 销售 从询盘到报价与跟进',heading)
text('客户询盘 → 核验公司官网与公开登记资料 → 查询商品及阶梯价 → 确定性报价 → Alibaba RFQ 英文回复 → 规则审核 → 对话修改与复审。')
text('<b>交付</b>　中英 PDF、双语 Excel、待审回复草稿和站内跟进待办。公开资料逐项留来源，不把官网自述当信用担保；金额取计算工具，运费、税费及未确认商务条件独立列明。')
text('同款接力 销售与运营共享事实',heading)
text('已报价询盘 → 同款商品候选事实与授权图片 → 用户确认 → 关联资料包和运营任务。岗位交接附记录编号、版本、负责人标签与待确认项；修改数量或事实后，受影响的报价与审核需要刷新。')
text('B 运营 从产品资料到平台草稿',heading)
text('确认事实 → 英文文案与 FAQ → 原图或示意图的方形、横版、竖版排版 → Amazon US Listing 草稿 → 风险标记与文字批注 → 第二轮改稿及复审。')
text('<b>交付</b>　英文资料、三种比例图片、ZIP 素材包与可下载审核报告。基础资料包与平台审核稿分开保存；最终平台改稿及前后变化在审核报告中，不将旧 ZIP 冒充更新后稿件。')
text('知识与合规 数据有依据 反馈能执行',heading)
text('企业知识按账号授权检索原文。美国、欧盟及西班牙、英国、加拿大案例按市场匹配，记录官方来源、适用条件和核验日期。结合平台要求、商务条款与敏感词，以文字批注和颜色标记反馈。缺少证据保持待确认，不补造认证或承诺。')
text('可重复现场演示与部署',heading)
text('以团队模拟 DESK-001 询盘演示：500件标准包装 → 1000件定制包装，报价小计 USD 5100.00（不含运税） → 同款资料包 → Amazon US 两轮审核 → 下载报价与素材。真实公开买家资料与模拟交易分别标注。')
text('运行：克隆 main 后执行 ./start.sh，首次创建自己的管理员；页面配置支持工具调用的模型。模型不可用时，工作台可运行计算和明确标注的本地模板；公开买家核验需联网。数据持久保存，仓库不包含账号、模型密钥或私有知识。')
story.append(Spacer(1,8))
text('作品：https://github.com/scp-xxg/foreign-trade-agent<br/>基于 HugAgentOS 开源社区版，保留 Powered by HugAgentOS、LICENSE 与 NOTICE。辅助审核不等于法律意见、认证或平台批准；图片不等于平台主图，草稿不自动发送或发布。',small)
SimpleDocTemplate(str(out),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=34,bottomMargin=30,title='SailAgent 外贸业务协作助手',author='SailAgent contributors').build(story)
print(str(out))
