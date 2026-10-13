"""Create a self-contained HTML slide deck from saved experiment evidence."""
from pathlib import Path
import json,csv,base64,io,html
from PIL import Image
ROOT=Path(__file__).resolve().parent.parent
REPORT=ROOT/'reports/comparison50'
if not REPORT.exists():REPORT=ROOT/'reports/comparison50'
OUT=ROOT/'experiment_recap_20261005';OUT.mkdir(exist_ok=True)
summary=json.loads((REPORT/'summary.json').read_text(encoding='utf-8'))
anns={a['image_index']:a for p in ((REPORT/'reference/annotations') if (REPORT/'reference/annotations').exists() else ROOT/'data/reference/annotations').glob('*.json') for a in [json.loads(p.read_text(encoding='utf-8'))]}
def asset(p):
 p=Path(p)
 if p.suffix=='.svg':return 'data:image/svg+xml;base64,'+base64.b64encode(p.read_bytes()).decode()
 with Image.open(p) as im:
  im=im.convert('RGB');im.thumbnail((1500,1300));buf=io.BytesIO();im.save(buf,format='JPEG',quality=88)
 return 'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()
def pic(index,kind='images'):
 a=anns[index];p=REPORT/'images'/a['file_name'] if kind=='images' else REPORT/kind/a['overlay_path'];return asset(p)
slides=[]
def slide(title,body,note='',kind=''):
 slides.append({'title':title,'body':body,'note':note,'kind':kind})
def columns(a,b):return f'<div class="columns"><div>{a}</div><div>{b}</div></div>'
def bullets(items):return '<ul>'+''.join('<li>'+x+'</li>' for x in items)+'</ul>'
def table(headers,rows):return '<table><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'
def chain(steps):return '<div class="chain">'+''.join(f'<div><b>{i+1:02d}</b><p>{s}</p></div>' for i,s in enumerate(steps))+'</div>'
def case(index,title,caption,note):
 body='<div class="case">'+''.join(f'<figure><figcaption>{label}</figcaption><img class="zoom" src="{pic(index,k)}" alt="{index:02d} {label}"></figure>' for k,label in [('images','原图'),('reference','候选参考'),('image25','API初稿'),('hybrid','自动精修')])+'</div><p class="takeaway">'+caption+'</p>'
 slide(title,body,note,'case-slide')
slide('建筑外立面缺陷分割<br>从 API 初稿到可比较实验',f'<div class="cover-copy"><p class="eyebrow">实验进度与过程回顾</p><p class="cover-sub">50张图 · 109个缺陷实例<br>OpenCV / image2.5 / image2.5＋OpenCV</p><p class="muted">整理日期 2026-10-05<br>结果截止已保存的2026-09-29批次；本次未重跑模型</p></div><img class="cover-image" src="{pic(34)}" alt="建筑墙面剥落样本">','本演示稿回顾过程和已保存证据，不新增模型请求。按左右方向键或空格翻页；N显示备注。','cover')
slide('实验已跑通；自动精修尚不能全面替代原稿',columns('<p class="hero-number">105<span>/109</span></p><p>API与精修版有结果的实例<br>46/50张实例齐全</p>','<p class="hero-number">+0.0227</p><p>精修后平均IoU提升</p><p class="hero-number negative small-number">−0.0451</p><p>边界F1下降</p>')+'<p class="takeaway">区域覆盖略有改善，但部分边界和细裂缝退化。</p>','指标相对于用户保留的候选参考；不是独立专家真值准确率。主指标采用全部109实例，缺失记0分。')
slide('要解决的问题：生成可追溯的原尺寸 mask',columns(bullets(['目标场景：后续处理5000+张建筑外立面缺陷图片。','当前先用50张固定样本比较方法，避免同时改变输入和算法。','输出必须与原图同宽高；一张图允许多个bbox、多个缺陷类型。']),bullets(['每个实例：独立mask、类型、bbox、面积与RLE。','每张图片：总mask、类别mask、彩色叠加图。','每次运行：耗时、token、估算费用、失败与重试记录。'])),'这轮比较使用已有bbox和类型，不评估从整图发现缺陷和分类的能力。尺寸正确是必要条件，但不保证轮廓准确。')
slide('从小样本试验，逐步冻结输入与评估口径',table(['阶段','做了什么','形成的决定'],[
 ['早期探索','小样本比较API模型，观察mask偏移','不把生成图的尺寸一致当作像素对齐'],
 ['参考版本迭代','按用户反馈补多bbox、多类型、垃圾、污渍等','保留v6候选标注，作为固定参考'],
 ['VS Code批量实验','先验证局部裁剪；先跑10张，再跑40张','固定bbox/类型，保留原始输入与变换'],
 ['自动精修与评估','OpenCV后处理，统计区域与边界指标','原API、候选、回退结果独立保存'],
 ['整理与发布','报告、代码、可选skill、流程图上线','可复现、可追溯，并记录未解决问题']]),'早期试验和当前固定50张不是完全同一实验口径，因此没有将早期模型结果拼入本次三方法排名。日期以文件中保存的批次版本为准，不推断每次聊天的精确时间。')
slide('“参考真值”来自多轮修订，仍有局限',columns('<p>原图 → 先检测bbox/类型 → 内置图像能力生成mask → 用户反馈 → 多轮修订 → 保留v6。</p>'+bullets(['修订涉及：漏检、错位、不连续区域拆分、地面垃圾与墙面污渍。','参考含多种生成方式，部分采用原图像素约束。','全部109实例参与后续固定评估。']),'<h3>必须保留的边界</h3>'+bullets(['未经独立专家逐像素验收。','三种待测方法只在评估阶段读取参考mask。','当前指标应称“与候选参考的一致度”。','下一轮需要独立人工标注与留出测试集。'])),'参考方法记录：独立目标拼图55、bbox引导28、整图按类别18、先验+原图像素约束7、墙面专用1。参考并不是单次同提示词自动生成。')
slide('三种方法共享同一套实例与坐标',table(['比较对象','分割输入','是否读取API mask','人工逐图引导'],[
 ['OpenCV基线','原图 + bbox + 类型/子类型','否','否'],
 ['image2.5','局部原图画布 + bbox坐标 + 类型提示','否','否；00/04沿用历史API试验'],
 ['image2.5 + OpenCV','原图 + 同一bbox/类型 + API实例mask','是','否']])+'<p class="takeaway">按原图哈希、实例ID、类别和bbox核对；独立保留每个实例。</p>','参考mask不参与待测分割。之前04号曾有人工轮廓辅助版本，未混入本次自动精修实验。VS Code是运行环境，不是模型。')
slide('方法一：OpenCV按缺陷外观分流',table(['缺陷','处理方法','主要风险'],[
 ['裂缝（含网状）','多尺度black-hat暗线 + 连通域','墙缝、管线和纹理误选'],
 ['锈迹 / 腐蚀','HSV / Lab颜色筛选','红漆、棕色基材混淆'],
 ['植物 / 地面垃圾','绿或暗色 / 相对地面背景的Lab色差','阴影、暗布料、亮地面'],
 ['污渍 / 渗漏 / 白桦','全局暗色 + 局部对比，追加黄棕响应','白色析出物可能漏检'],
 ['剥落 / 破损','Lab聚类选种子 + GrabCut','前背景倒置、空腔与基材混淆']])+'<p class="foot">裂缝原分辨率；区域ROI长边最多1000像素。还原到原图后导出实例mask及并集。</p>','运行入口为skill/scripts/segment.py；这是纯bbox基线，不是assisted人工引导版。记录显示50张109实例、运行约46.8秒（另精修时间不是这个数）。')
slide('方法二：先构造局部画布，再还原原图坐标',chain(['bbox外扩上下文<br>记录原图偏移','宽高比大于3？<br>长边分4段','单面板 / 2×2拼图<br>统一1024画布','每bbox一次API<br>返回黑白mask','按几何记录逆映射<br>原尺寸裁框'])+'<div class="columns compact"><p>横向边距：bbox宽的20%，至少12px。<br>纵向边距：bbox高的2.5%，至少12px。</p><p>阈值128；最近邻还原；拒绝异常长宽比。<br>保存真实上传画布、原始返回、几何和裁框前mask。</p></div><p class="takeaway">几何逆变换可以复现；模型重绘造成的内容偏移仍可能存在。</p>','代码：batch_local.py和local_crop_trial.py。模型是服务商标识的gpt-image-2.5，底层身份未独立验证。此处不做OpenCV修边。')
slide('API批量处理：补齐请求与修好分割是两件事',table(['后40张的轮次','累计请求','成功实例 / 91','仍缺失'],[
 ['首次运行',91,63,28],['重试失败28项',119,80,11],['再重试失败11项',130,87,4]
 ])+'<p>前10张共有18个实例：16个本批新生成，2个沿用已有成功试验。<br>合计：105/109实例有mask；缺失为25/ID2、27/ID1、30/ID1、39/ID1。</p><p class="takeaway">重试仅针对失败记录；已生成但错位的mask不会因重试自动修好。</p>','首次失败主要有HTTP500/503及SSL错误。最后4个仍失败，不把空白输出当作无缺陷。全部两批请求共152次，不含两项历史复用的原始请求。')
slide('方法三：API先验约束下，在原图上精修',chain(['保留API原mask<br>校验bbox和尺寸','膨胀为搜索带<br>4–32原图像素','裂缝：找暗线<br>区域：GrabCut','逆变换与裁框<br>保存候选','异常检查<br>采用或回退'])+bullets(['区域类用API腐蚀内核作为确定前景；可能同时锁住原有误选。','搜索带不能可靠找回远离API候选的漏检。','区域长边最多1200像素；裂缝保持原分辨率；无新增API调用。']),'默认不自动启用skill。当前精修是可选程序，与含人工轮廓的精修模式分开。')
slide('93个候选被采用，不代表93个质量改善',columns('<h3>异常筛选</h3>'+bullets(['空候选 → 回退。','面积比 <0.35 或 >2.5 → 回退。','候选与原API的IoU <0.10 → 回退。','求解异常 / 种子不足 → 回退。']),'<p class="hero-number">93<span>采用</span></p><p class="hero-number small-number">12<span>回退</span></p><p>原稿、候选、最终选用mask分别保存。<br>105项处理耗时合计约59秒。</p>')+'<p class="takeaway">回退保护的是结果稳定性；原API本身可能错误。</p>','保留raw_instance_masks、candidate_instance_masks、instance_masks。Windows报表文件替换出现WinError5后，增加重试和续跑兼容；已保存13张后续跑完成50张。')
slide('评估同时看区域、漏选和边界',table(['指标','含义','本次口径'],[
 ['IoU / Dice','预测与参考区域的重叠程度','按实例计算后等权平均'],
 ['精确率','选中的像素有多少属于参考缺陷','低值提示误选较多'],
 ['召回率','参考缺陷像素有多少被选中','高值可能来自更宽泛的覆盖'],
 ['边界F1','预测轮廓与参考轮廓是否贴合','原图2像素容差'],
 ['缺失处理','API失败不从主表悄悄剔除','全部109计0分；另报共同105']]),'不是检测准确率，也不采用大量背景像素主导的pixel accuracy。区域指标上升和边界指标下降可能同时出现。')
rows=[]
for key,label in [('opencv','OpenCV'),('image25','image2.5'),('hybrid','image2.5＋OpenCV')]:
 a=summary['methods'][key]['all_instances'];rows.append([label,*[f'{a["macro_"+m]:.3f}' for m in ['iou','dice','precision','recall','boundary_f1']]])
slide('全109实例：精修提高区域指标，边界指标下降',table(['方法','IoU','Dice','精确率','召回率','边界F1'],rows)+'<div class="columns compact"><p><b>OpenCV</b><br>召回高，但误选也较多。</p><p><b>image2.5</b><br>边界F1最高；不代表每张都对齐。</p></div><p class="takeaway">混合方法平均IoU最高，但不能据此判定它在所有缺陷上更好。</p>','数值从summary.json自动读取，保持与报告一致。此前柱状图已按用户要求移除，本稿也使用表格。')
slide('排除请求失败后，区域指标的排序仍相同',table(['方法','共同105实例 IoU','共同105实例 Dice','共同105实例 边界F1'],[[label,*[f'{summary["methods"][key]["common_available_instances"]["macro_"+m]:.3f}' for m in ['iou','dice','boundary_f1']]] for key,label in [('opencv','OpenCV'),('image25','image2.5'),('hybrid','image2.5＋OpenCV')]])+'<p class="takeaway">105个实例中：61个IoU提升，31个下降，13个不变。</p><p>“提升/下降”按数值正负统计，未设置最小有效变化幅度。<br>实例级复核比单看整体平均更能定位问题。</p>','共同子集只包含三种方法均有输出的实例，不能与全109指标混用。采用93个候选，但最终IoU改变92项；并非统计矛盾。')
case(33,'改善案例 · 33号 ID1：锈迹区域更接近参考','IoU 0.533 → 0.799（+0.266）；边界F1增加0.096。','数值来自refinement_changes.csv中33/ID1，图片展示整张图，包括另一个实例。结论仅针对ID1和当前参考，不代表整图所有实例均有同等改善。')
case(29,'退化案例 · 29号 ID1：裂缝被过度收窄','IoU 0.779 → 0.239（−0.540）；边界F1下降0.126。','这说明自动暗线搜索与当前参考区域可能明显不一致。与原API的异常阈值没有挡住这次退化，不应只放宽或扩大搜索范围。')
case(17,'回退案例 · 17号：原有错位仍然保留','候选与API原稿分歧过大 → raw_fallback；最终结果等于原API。','回退时与API的IoU约0.022，触发阈值。自动回退不能修复原API错位；需要定位引导或重新分割。')
slide('成本与耗时：已知值、未知值分别记录',table(['项目','当前记录','不能推断什么'],[
 ['两批API调用','152次；其中49次费用未知','失败请求不能直接视作免费'],
 ['已知费用估算','¥5.15','非平台实扣；不含两项历史复用与早期弃用试验'],
 ['纯OpenCV基线','总运行约46.8秒','不含人工复核与早期方法开发'],
 ['API后处理','逐图处理耗时合计约59秒','不含本次评估、报表及人工验收'],
 ['token','按服务端返回记录，缺失为null','不能把未知token记为0']]),'价格依据实验时用户提供的配置每请求0.05元，是历史估算，不能当作今后5000张的保证价格。大批量成本还受实例数、失败率、返工和人工验收影响。')
slide('已形成可复用的程序与审查材料',columns(bullets(['batch_local.py：API局部裁剪与断点续跑。','refine_api_masks.py：可选OpenCV后处理。','compare_three_methods.py：只读评估和HTML对比。','skill：记录模式选择与方法边界，不默认开启精修。']),'<h3>在线材料</h3><p><a href="https://mo0407.github.io/FacadeFixer_mask_api/reports/comparison50/comparison.html" target="_blank">完整50张对比报告 ↗</a></p><p><a href="https://mo0407.github.io/FacadeFixer_mask_api/reports/comparison50/workflows.html" target="_blank">三种方法详细流程图 ↗</a></p><p><a href="https://github.com/mo0407/FacadeFixer_mask_api" target="_blank">GitHub代码与文档 ↗</a></p><p class="muted">本演示稿图片已内嵌；离线可翻页。<br>以上在线链接需要网络。</p>'),'仓库不包含API密钥。报告已补四种mask来源、原尺寸黑白mask及统计。GitHub Pages上线过程中补齐50张被忽略规则漏掉的原图，并修复README中文编码。')
slide('下一阶段：先处理难例，再讨论5000张推广',table(['优先级','建议工作','验收方式'],[
 ['P1','补齐4个API失败实例，单独解决请求稳定性','分开记录请求成功率与分割质量'],
 ['P1','对裂缝错位、空腔、污渍设专项复核集','逐实例看区域与边界，保留原稿'],
 ['P2','引入明确的人工/视觉引导，作为独立实验','记录额外引导成本，不混入自动结果'],
 ['P2','建立独立专家标注及未调参的留出集','按缺陷类别比较，避免只看总体均值'],
 ['P3','再扩大批量并估算生产成本','包含bbox数、重试、返工和人工验收']])+'<p class="takeaway">当前可用作实验初稿与审查流程；尚不适合无人复核地替换全部标注。</p>','这些是后续建议，尚未完成；本次没有重跑API、修订mask或新增费用。')

for key,title in [('opencv','附录 · OpenCV完整数据流'),('image25','附录 · image2.5完整数据流'),('hybrid','附录 · API＋OpenCV完整数据流')]:
 slide(title,f'<div class="flow-wrap"><img class="zoom flow" src="{asset(REPORT/"flows"/(key+".svg"))}" alt="{title}"><p>点击流程图放大。<br>包含输入、类别分支、尺度变换、异常处理和输出文件。<br><br>这是已有流程图的原始SVG，放大不会模糊。</p></div>','详细流程依据实现代码整理。点击图像打开查看器，可使用浏览器缩放；Esc关闭。','appendix')

css='''*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;background:#17232c;color:#17313d;font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif}body{overflow:hidden}#viewport{position:absolute;inset:0 0 60px;display:flex;align-items:center;justify-content:center}#stage{width:1600px;height:900px;flex-shrink:0;transform-origin:center;position:relative;background:#f8f7f2;box-shadow:0 18px 80px #0006}.slide{position:absolute;inset:0;padding:64px 84px 66px;display:none;overflow:hidden}.slide.active{display:block}.slide h1{font-size:52px;line-height:1.22;letter-spacing:-1px;font-weight:650;margin:0 0 42px;max-width:1370px}.slide h3{font-size:30px;margin:0 0 22px}.content{font-size:28px;line-height:1.62}.content p{margin:0 0 22px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:80px}.columns.compact{margin-top:32px;font-size:27px;gap:42px}ul{margin:0;padding-left:30px}li{margin-bottom:24px}.muted,.foot{color:#62747b}.foot{font-size:23px;margin-top:28px!important}.takeaway{border-left:6px solid #ba5a39;padding:12px 0 12px 25px;margin-top:32px!important;font-size:29px;font-weight:550}.hero-number{font-size:100px!important;font-weight:650;line-height:1.05!important;color:#0e766e;letter-spacing:-4px;margin-bottom:18px!important}.hero-number span{font-size:32px;letter-spacing:0;color:#60747a;margin-left:12px}.small-number{font-size:68px!important}.negative{color:#a34a31}table{border-collapse:collapse;width:100%;font-size:25px;line-height:1.45}th{text-align:left;color:#61737a;font-size:22px;border-bottom:2px solid #a8b6b7;padding:16px 16px 20px 0}td{padding:21px 16px 21px 0;border-bottom:1px solid #d1d8d5;vertical-align:top}td:first-child{font-weight:600;color:#124d54;min-width:180px}a{color:#0a7975;text-underline-offset:6px}footer{position:absolute;left:84px;right:84px;bottom:25px;display:flex;justify-content:space-between;font-size:18px;color:#6b7c80}.cover h1{font-size:65px;max-width:980px;margin-top:90px;position:relative;z-index:2}.cover-image{position:absolute;right:65px;top:55px;width:460px;height:780px;object-fit:contain;opacity:.9}.cover-copy{max-width:860px;position:relative;z-index:2}.eyebrow{font-size:24px;color:#0e766e;letter-spacing:5px}.cover-sub{font-size:31px;margin-top:50px!important}.cover .muted{font-size:22px;margin-top:60px!important}.chain{display:grid;grid-template-columns:repeat(5,1fr);gap:32px;margin:45px 0}.chain>div{position:relative;border-top:3px solid #0e766e;padding-top:15px}.chain>div:not(:last-child)::after{content:'→';position:absolute;right:-28px;top:48px;color:#718986}.chain b{font-size:22px;color:#0e766e}.chain p{font-size:26px;margin-top:20px}.case{display:grid;grid-template-columns:repeat(4,1fr);gap:22px}.case figure{margin:0}.case figcaption{font-size:24px;color:#5d7077;margin-bottom:12px}.case img{width:100%;height:430px;object-fit:contain;background:#e9eeeb}.case-slide .takeaway{font-size:26px}.zoom{cursor:zoom-in}.flow-wrap{display:flex;gap:70px;align-items:center}.flow{width:850px;height:630px;object-fit:contain;background:white}.flow-wrap p{width:440px;font-size:28px}#controls{height:60px;position:absolute;bottom:0;left:0;right:0;display:flex;align-items:center;justify-content:center;gap:14px;background:#17232c;color:#dce9e9;font-size:15px}button,select{font:inherit;border:1px solid #567079;background:#243842;color:#f1f7f6;border-radius:5px;padding:7px 12px;cursor:pointer}button:focus-visible,select:focus-visible{outline:3px solid #3bd1b3}select{max-width:400px}#progress{position:absolute;bottom:60px;left:0;height:3px;background:#43b7a2;transition:width .15s}#notes{display:none;position:fixed;bottom:65px;left:5%;right:5%;padding:24px;background:#102630f5;color:#fff;font-size:20px;line-height:1.6;border:1px solid #78959f;z-index:5}#notes.show{display:block}dialog{border:0;border-radius:8px;background:#fff;padding:15px;max-width:96vw;max-height:96vh}dialog::backdrop{background:#000b}dialog img{display:block;max-width:90vw;max-height:85vh;object-fit:contain}dialog button{display:block;margin:5px 0 10px auto}.print-notes{display:none}@media print{@page{size:1600px 900px;margin:0}html,body{height:auto;background:white;overflow:visible}#viewport{position:static;display:block}#stage{width:1600px;height:auto;transform:none!important;box-shadow:none}.slide{position:relative;display:block!important;width:1600px;height:900px;break-after:page}#controls,#progress,#notes,dialog{display:none!important}}'''
from recap_reading_layout import configure, CSS, JS
configure(slides, asset, REPORT)
css += CSS
parts=[]
for i,s in enumerate(slides):
 parts.append(f'<section class="slide {s["kind"]}" data-title="{html.escape(s["title"].replace("<br>"," "),quote=True)}" data-note="{html.escape(s["note"],quote=True)}" aria-label="第{i+1}页"><h1>{s["title"]}</h1><div class="content">{s["body"]}</div><footer><span>外立面缺陷 mask 实验回顾 · 2026-10-05</span><span>{i+1:02d} / {len(slides):02d}</span></footer></section>')
js='''const slides=[...document.querySelectorAll('.slide')],sel=document.querySelector('#jump');let index=0;slides.forEach((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${i+1}. ${s.dataset.title}`;sel.append(o)});function size(){const v=document.querySelector('#viewport');document.querySelector('#stage').style.transform=`scale(${Math.min(v.clientWidth/1600,v.clientHeight/900)})`}function go(n){index=Math.max(0,Math.min(slides.length-1,n));slides.forEach((s,i)=>{s.classList.toggle('active',i===index);s.setAttribute('aria-hidden',i!==index)});sel.value=index;document.querySelector('#count').textContent=`${index+1} / ${slides.length}`;document.querySelector('#progress').style.width=((index+1)/slides.length*100)+'%';document.querySelector('#notes').textContent=slides[index].dataset.note;history.replaceState(null,'','#slide-'+(index+1))}document.querySelector('#prev').onclick=()=>go(index-1);document.querySelector('#next').onclick=()=>go(index+1);sel.onchange=()=>go(+sel.value);document.querySelector('#noteButton').onclick=()=>document.querySelector('#notes').classList.toggle('show');document.querySelector('#full').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen()}catch(e){alert('当前浏览器不支持全屏，请使用F11。')}};document.querySelector('#print').onclick=()=>window.print();const dialog=document.querySelector('dialog');document.querySelectorAll('.zoom').forEach(im=>{im.tabIndex=0;im.setAttribute('role','button');im.onclick=()=>{dialog.querySelector('img').src=im.src;dialog.querySelector('img').alt=im.alt;dialog.showModal()};im.onkeydown=e=>{if(e.key==='Enter')im.click()}});document.querySelector('#close').onclick=()=>dialog.close();document.addEventListener('keydown',e=>{if(dialog.open||['SELECT','INPUT','TEXTAREA'].includes(document.activeElement.tagName))return;if(['ArrowRight','ArrowDown','PageDown',' '].includes(e.key)){e.preventDefault();go(index+1)}if(['ArrowLeft','ArrowUp','PageUp'].includes(e.key)){e.preventDefault();go(index-1)}if(e.key==='Home')go(0);if(e.key==='End')go(slides.length-1);if(e.key.toLowerCase()==='n')document.querySelector('#noteButton').click()});window.addEventListener('resize',size);go((+location.hash.replace('#slide-','')||1)-1);size();'''
js=JS
doc='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>外立面缺陷Mask实验回顾</title><style>'+css+'</style></head><body><main id="viewport"><div id="stage">'+''.join(parts)+'</div></main><div id="progress"></div><aside id="notes" aria-live="polite"></aside><nav id="controls" aria-label="演示控制"><button id="prev" aria-label="上一页">← 上一页</button><span id="count"></span><button id="next" aria-label="下一页">下一页 →</button><select id="jump" aria-label="目录跳转"></select><button id="noteButton">备注 N</button><button id="full">全屏</button><button id="print">打印 / PDF</button></nav><dialog><button id="close">关闭 Esc</button><img alt="放大图片"></dialog><script>'+js+'</script></body></html>'
(OUT/'index.html').write_text(doc,encoding='utf-8')
(OUT/'slide_content.json').write_text(json.dumps([{'page':i+1,'title':s['title'].replace('<br>',' '),'notes':s['note']} for i,s in enumerate(slides)],ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Created {len(slides)} slides; self-contained HTML {len(doc.encode())/1024/1024:.1f} MiB; {OUT / "index.html"}')
if __name__=='__main__':pass
