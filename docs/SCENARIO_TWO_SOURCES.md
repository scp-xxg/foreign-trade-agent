# 场景二真实资料示例：Raspberry Pi 5

核验日期：2026-10-21。

本示例用于“导入产品资料与原图 → 确认事实 → 制作商品介绍、图片和 FAQ”的验收。产品、官网和照片均可公开核验。采购条件未提供，不能据此生成可执行销售报价或宣称本项目拥有经销授权。

## 产品事实

唯一规格来源为 [Raspberry Pi 官方产品页](https://www.raspberrypi.com/products/raspberry-pi-5/) 的 Specification 部分。资料包记录 8 个简短事实：型号、处理器、显示输出、USB 接口、有线网络、无线网络、蓝牙和电源。每条记录包含中英字段、来源 URL、核验日期和不超过 120 字符的短证据；没有保存官网整页或宣传文案。

尚未确认：具体 RAM 容量、销售授权、价格与 MOQ、库存与交期、包装配件、保修和目标市场合规结论。图片外观不用于推断这些条件。

## 照片许可与署名

- 文件标题：Raspberry Pi 5.jpg
- 作者：[SimonWaldherr](https://commons.wikimedia.org/wiki/User:SimonWaldherr)
- 来源：[Wikimedia Commons 文件说明页](https://commons.wikimedia.org/wiki/File:Raspberry_Pi_5.jpg)
- 核验版本：[固定页面版本](https://commons.wikimedia.org/w/index.php?title=File:Raspberry_Pi_5.jpg&oldid=1010202564)
- 许可：[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)；[完整条款](https://creativecommons.org/licenses/by/4.0/legalcode.en)
- 原图：[原始 JPEG](https://upload.wikimedia.org/wikipedia/commons/e/e7/Raspberry_Pi_5.jpg)，4600 × 3400 像素。
- 入库方式：原始字节保留，没有裁剪、调色或抹去标志。已目视核对电路板上的 Raspberry Pi 5 型号。

图片保留独立 CC BY 4.0 许可，不受仓库软件许可证重新授权。页面、素材包和派生排版图需保留作者、标题、来源、许可链接，并说明修改。许可允许分享和改编，但不表示摄影者或品牌方为项目背书，也不授予商标权。不要把该照片称为“无版权图片”或团队原创。

可复制的原图署名：

> Photo: SimonWaldherr, Raspberry Pi 5.jpg (CC BY 4.0). Original image unchanged. Source: https://commons.wikimedia.org/wiki/File:Raspberry_Pi_5.jpg License: https://creativecommons.org/licenses/by/4.0/

生成排版图时，将原图未修改说明改为：Layout and text added; original photo retained.

## 文件

均位于 extensions/foreign_trade/demo_product/：

- product_facts.csv：带 UTF-8 BOM 的机器可导入事实表。
- product_facts.txt：同一组事实的纯文本资料。
- raspberry-pi-5-original.jpg：授权真实照片。
- sources.json：事实、来源、摄影者、许可、原图地址、时间和 SHA-256。
- PHOTO_LICENSE.txt：可随下载资料包分发的第三方照片许可说明。

照片 SHA-256：77a724485f6b48408aacf2e42806783e1c9448997a9e9627905fe2d3f2ada264。

事实表和照片用于资料导入测试；没有添加到现有模拟报价产品目录，也没有改动其价格规则。
