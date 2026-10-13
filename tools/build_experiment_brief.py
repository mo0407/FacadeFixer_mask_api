"""Build a concise local-only experiment recap from saved evidence."""
from pathlib import Path
import json,html,base64,io
import csv
from PIL import Image
from recap_reading_layout import JS
ROOT=Path(__file__).resolve().parent.parent
REPORT=ROOT/'reports/comparison50'
OUT=ROOT/'reports/experiment_brief';OUT.mkdir(exist_ok=True)
summary=json.loads((REPORT/'summary.json').read_text(encoding='utf8'))
anns={a['image_index']:a for p in ((REPORT/'reference/annotations') if (REPORT/'reference/annotations').exists() else ROOT/'data/reference/annotations').glob('*.json') for a in [json.loads(p.read_text(encoding='utf8'))]}
def image(index,kind):
 a=anns[index];p=REPORT/kind/a['overlay_path']
 with Image.open(p) as im:
  im=im.convert('RGB');im.thumbnail((1300,1300));b=io.BytesIO();im.save(b,format='JPEG',quality=90)
 return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
slides=[]
def add(title,body,note=''):slides.append((title,body,note))
add('建筑外立面缺陷分割<br>实验回顾 · 精简版','''<p class="lead">比较三种方法，回答一个问题：<br>怎样更可靠地生成缺陷mask？</p><div class="facts"><p><strong>50</strong>张测试图片</p><p><strong>109</strong>个缺陷实例</p><p><strong>3</strong>种处理方法</p></div><p class="takeaway">目前已完成批量实验。API后精修提高了平均区域重合度，但并非所有缺陷都会改善。</p><p class="muted">整理于2026年10月9日 · 基于已保存结果，未重新运行模型</p>''')
add('01　这次实验比较什么','''<p>给定同一张原图、同一组检测框和缺陷类型，比较不同方法生成的mask。</p><div class="flow"><span>原图＋缺陷框＋类型</span><b>→</b><span>三种方法分别处理</span><b>→</b><span>mask＋原图叠加图</span></div><p><b>mask</b>表示缺陷具体覆盖哪些像素。叠加图把这些像素标在原图上，方便检查漏选、误选和偏移。</p><p class="muted">本轮只比较分割效果，不评价检测框和缺陷类型是否判断正确。</p>''')
add('02　实验是怎样推进的','''<ol class="timeline"><li><b>先做小样本试验</b><span>比较生成效果，发现轮廓偏移和漏检问题。</span></li><li><b>固定50张样本和参考标注</b><span>根据反馈反复修订，统一检测框、类型和实例编号。</span></li><li><b>批量运行三种方法</b><span>先验证小批次，再扩展到50张，随后增加自动精修。</span></li><li><b>整理结果并比较</b><span>同时检查量化指标和典型图片，记录改善与退化。</span></li></ol>''')
add('03　三种方法，各自做什么','''<div class="method"><h3>OpenCV</h3><p class="route">原图＋缺陷框／类型 → 按颜色、明暗和纹理找缺陷 → mask</p><p>用图像处理规则直接筛选像素。速度快，但容易把阴影、墙缝或背景纹理一起选中。</p></div><div class="method"><h3>image2.5</h3><p class="route">裁出每个缺陷附近的图像 → API生成mask → 放回原图</p><p>让模型一次关注一个目标。局部裁剪有助于看清缺陷，但模型生成的轮廓仍可能偏移。</p></div><div class="method"><h3>image2.5＋OpenCV</h3><p class="route">API初稿 → 结合原图调整边缘 → 检查后保留或回退</p><p>尝试让已有mask更贴合原图。如果初稿漏掉大片区域，精修也不一定能找回来。</p></div>''')
add('04　目前完成到哪一步','''<table><thead><tr><th>项目</th><th>当前状态</th></tr></thead><tbody><tr><td>OpenCV基线</td><td>109个实例均有输出</td></tr><tr><td>API与自动精修</td><td>105个实例有输出，4个API实例仍失败</td></tr><tr><td>完整图片</td><td>API与精修版有46／50张实例齐全</td></tr><tr><td>成果整理</td><td>已形成对比报告、处理代码和可选精修skill</td></tr></tbody></table><p class="takeaway">“生成成功”只表示有结果，不能直接当作“分割准确”。</p>''')
rows=[]
for key,label in [('opencv','OpenCV'),('image25','image2.5'),('hybrid','image2.5＋OpenCV')]:
 m=summary['methods'][key]['all_instances'];rows.append(f'<tr><td>{label}</td><td>{m["macro_iou"]:.3f}</td><td>{m["macro_boundary_f1"]:.3f}</td></tr>')
add('05　结果说明了什么','<table><thead><tr><th>方法</th><th>区域重合度 · IoU ↑</th><th>边界贴合度 · F1 ↑</th></tr></thead><tbody>'+''.join(rows)+'''</tbody></table><p>两个指标都是越高越好：前者看选中的区域是否一致，后者看轮廓是否贴合。</p><p class="takeaway">精修后的区域重合度最高，API初稿的边界贴合度最高。不能仅凭一个平均指标决定哪种方法最好。</p><p class="muted">按全部109个实例平均，缺失项计0分。参考标注来自多轮修订，尚未经独立专家验收，因此这些数值表示与当前参考的一致程度。</p>''')
cases=''
for index,title,desc in [(33,'改善案例：锈迹','33号ID1的区域重合度从0.533升至0.799。'),(29,'退化案例：裂缝','29号ID1的区域重合度从0.779降至0.239，精修后选中的裂缝过窄。')]:
 cases+=f'<h3>{title}</h3><div class="pictures">'+''.join(f'<figure><img src="{image(index,kind)}" alt="{index} {label}"><figcaption>{label}</figcaption></figure>' for kind,label in [('reference','当前参考'),('image25','API初稿'),('hybrid','自动精修')])+f'</div><p>{desc}</p>'
add('06　为什么仍需要逐图检查',cases,'图片展示整图叠加结果，数值对应所述实例ID。点击图片可放大、缩放和拖动。')
add('07　下一步先做什么','''<ol class="timeline"><li><b>补齐缺失结果</b><span>重试剩余4个失败实例，先完成全量输出。</span></li><li><b>集中处理难例</b><span>优先检查裂缝偏移、污渍漏选和剥落边缘，再调整精修方法。</span></li><li><b>建立独立验证集</b><span>由人工复核参考标注，用未参与调参的图片检验效果。</span></li></ol><p class="takeaway">当前更适合“自动生成初稿＋人工复核”。先把稳定性和难例处理做好，再扩展到5000张。</p><p class="muted">以上为后续计划，尚未在本次整理中执行。</p>''')
css='''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#e8ece9;color:#17313d;font-family:"Microsoft YaHei",system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:30px 24px 95px}.slide{position:relative;background:#faf9f5;margin-bottom:25px;padding:52px 62px 60px;scroll-margin-top:20px}h1{font-size:38px;line-height:1.4;margin:0 0 28px}h3{font-size:25px;margin:24px 0 12px}p{font-size:23px;line-height:1.8;margin:16px 0}.lead{font-size:29px}.muted{font-size:18px;color:#62747b}.takeaway{border-left:5px solid #b76143;padding-left:22px;margin-top:28px;font-weight:600}.facts{display:flex;gap:75px;margin:28px 0}.facts strong{font-size:60px;display:block;color:#10796e}.flow{display:flex;align-items:center;gap:18px;font-size:21px;padding:28px 0;color:#10796e}.flow span{border-bottom:2px solid #10796e;padding-bottom:10px}.timeline{padding-left:28px}.timeline li{font-size:24px;padding:12px 0 18px 10px}.timeline span{display:block;font-size:22px;line-height:1.7;color:#52666c;margin-top:8px}.method{border-top:1px solid #ccd6d1;padding:10px 0}.method .route{color:#10796e;font-weight:600}table{border-collapse:collapse;width:100%;font-size:23px;line-height:1.6}th,td{text-align:left;border-bottom:1px solid #ccd6d1;padding:18px 16px}th{font-size:20px;color:#62747b}.pictures{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}figure{margin:0}figure img{width:100%;height:300px;object-fit:contain;background:#e7eae6}figcaption{font-size:19px;text-align:center;margin:10px 0;color:#52666c}footer{font-size:16px;color:#78908e;text-align:right;margin-top:28px}button,select{font:inherit;border:1px solid #64817d;background:#253d42;color:white;border-radius:5px;padding:8px;cursor:pointer}#controls{position:fixed;bottom:0;left:0;right:0;display:flex;justify-content:center;align-items:center;gap:12px;background:#17313d;color:white;padding:12px;z-index:10}#jump{max-width:340px}#progress{position:fixed;bottom:64px;left:0;height:3px;background:#36b5a0;z-index:11}#notes{display:none;position:fixed;bottom:70px;left:8%;right:8%;padding:22px;background:#17313df5;color:white;z-index:12;font-size:20px}#notes.show{display:block}dialog{width:96vw;height:94vh;max-width:96vw;max-height:94vh;padding:0;border:0;background:#17313d;color:white}dialog::backdrop{background:#000b}.viewer-tools{height:60px;display:flex;gap:10px;align-items:center;padding:8px}.viewer-tools #close{margin-left:auto}.viewer-canvas{height:calc(100% - 60px);overflow:auto;touch-action:none;cursor:grab;background:#d6ddda}.viewer-canvas.dragging{cursor:grabbing}.viewer-canvas img{display:block;max-width:none;max-height:none;margin:auto;user-select:none}@media(max-width:760px){main{padding:10px 10px 120px}.slide{padding:25px 20px}h1{font-size:28px}p{font-size:20px}.flow,.facts{flex-wrap:wrap;gap:20px}.pictures{grid-template-columns:1fr}.facts strong{font-size:42px}table{font-size:18px}th,td{padding:10px 5px}#controls{flex-wrap:wrap}.viewer-tools span{display:none}}@media print{@page{size:A4 landscape;margin:10mm}body{background:white}main{max-width:none;padding:0}.slide{break-after:page;padding:20px;margin:0}#controls,#progress,#notes,dialog{display:none!important}p{font-size:18px}h1{font-size:28px}figure img{height:210px}}'''
from brief_flowcharts_medium import attach, CSS as FLOW_CSS
attach(slides,OUT)
css+=FLOW_CSS
class_rows=list(csv.DictReader((REPORT/'classes.csv').read_text(encoding='utf-8-sig').splitlines()))
instance_rows=list(csv.DictReader((REPORT/'instances.csv').read_text(encoding='utf-8-sig').splitlines()))
names={'C':'裂缝','P':'剥落','S':'破损','T':'锈迹','R':'腐蚀','D':'污染物','L':'白桦','V':'植物'}
by_class={(r['method'],r['class_code']):r for r in class_rows}
methods=['opencv','image25','hybrid'];class_table=[]
for code in ['C','P','S','T','R','D','L','V']:
 n=int(by_class['opencv',code]['instances']);scores=[float(by_class[m,code]['macro_iou']) for m in methods];cells=[]
 for method,score in zip(methods,scores):
  entries=[r for r in instance_rows if r['class_code']==code and r['method']==method]
  assert len(entries)==n
  assert abs(sum(float(r['iou']) for r in entries)/n-score)<1e-9
  available=sum(r['missing'].lower()=='false' for r in entries)
  bf1=float(by_class[method,code]['macro_boundary_f1'])
  mark=' class="leading-iou"' if score==max(scores) else ''
  cells.append(f'<td><span{mark}>IoU {score:.3f}</span><br><span class="class-secondary">边界F1 {bf1:.3f}<br>有输出 {available}/{n}</span></td>')
 class_table.append(f'<tr><th scope="row">{names[code]} <small>{code}</small></th><td>{n}</td>'+''.join(cells)+'</tr>')
assert sum(int(by_class['opencv',c]['instances']) for c in names)==109
stats='''<p>按缺陷实例统计，而不是按图片统计；一张图片可以包含多种缺陷。每格列出区域重合度、边界贴合度和有输出的实例数。</p><div class="class-scroll"><table class="class-stats"><thead><tr><th>缺陷类型</th><th>实例数</th><th>OpenCV</th><th>image2.5</th><th>image2.5＋OpenCV</th></tr></thead><tbody>'''+''.join(class_table)+'''</tbody></table></div><p class="muted">绿色加粗仅标记该类最高平均IoU，不表示全面最优。有输出也不代表分割合格；缺失实例按0分计入均值。边界F1采用原图2像素容差。</p><p><b>主要观察：</b>混合方法在8类中的6类平均IoU最高，OpenCV在污染物和破损上最高。API初稿在8类中的6类边界F1最高，混合方法在裂缝和剥落上最高。</p><p><b>优先改进：</b>合并后的裂缝类，三种方法平均IoU均低于0.18，仍是共同难点。</p><p class="muted">腐蚀、植物各仅3个实例，白桦仅2个，不能据此推广排名。污染物D合并墙面污渍与地面垃圾；类别于2026年10月13日调整：原裂缝与网裂合并为裂缝C，共23例；原L类改名为白桦，共2例。实例mask未改动。所有指标比较的仍是未经独立专家验收的候选参考。</p>'''
slides[6]=(slides[6][0].replace('06','07',1),slides[6][1],slides[6][2])
slides[7]=(slides[7][0].replace('07','08',1),slides[7][1],slides[7][2])
slides.insert(6,('06　每种缺陷的处理情况',stats,'来源：classes.csv与instances.csv，按类别、方法核对全部109个实例。IoU与边界F1为实例等权平均，缺失计0，不是检测分类准确率。'))
time_cost=json.loads((REPORT/'time_cost.json').read_text(encoding='utf8'))
cv=time_cost['opencv'];api=time_cost['api'];hy=time_cost['hybrid']
timing=f'''<p>以下比较本次50张实验的程序记录。混合方法复用API初稿，只新增离线精修步骤。</p><div class="class-scroll"><table class="cost-table"><thead><tr><th>方法</th><th>处理范围</th><th>记录耗时</th><th>API费用</th></tr></thead><tbody><tr><th>OpenCV</th><td>50张／109实例</td><td><b>{cv['wall_seconds']:.1f}秒</b><br>完整基线运行用时</td><td><b>¥0</b><br>不调用API</td></tr><tr><th>image2.5</th><td>152次请求，含重试<br>最终105／109实例有输出</td><td><b>{api['attempt_seconds_sum']/60:.1f}分钟</b><br>逐次请求任务耗时之和</td><td>已知估算 <b>¥{api['known_cost_estimate_cny']:.2f}</b><br>另有{api['unknown_cost_attempts']}次请求费用未知</td></tr><tr><th>image2.5＋OpenCV</th><td>精修已有105个实例</td><td>API阶段同上<br>精修额外约 <b>{hy['additional_processing_seconds_sum']:.1f}秒</b><br>逐图处理耗时之和</td><td>沿用API阶段费用<br>精修新增 <b>¥0</b></td></tr></tbody></table></div><h3>这些时间应该怎样理解？</h3><p>OpenCV的46.8秒是一次运行的实际经过时间；API的109.1分钟是152次请求任务耗时相加，包含重试及单次结果处理，<b>不是从启动到完成的实际等待时长</b>。并发和多轮重试间隔会影响实际等待时间，因此不能直接计算提速倍数。</p><h3>这些费用包含什么？</h3><p>¥5.15是已知API费用的估算部分，并非平台实扣总账单。失败请求费用未知不能当作免费；上述API时间与费用均不含两项历史复用结果的原始请求，以及更早舍弃的试验。</p><p class="takeaway">OpenCV无需API费用；在已有API结果上做精修，本次只额外增加约59秒的处理记录，不增加API费用。</p><p class="muted">不包含人工复核、算法开发、电脑／电力成本及报告整理。API实扣金额和整批实际经过时间未完整记录。数据来自历史运行，不是新一轮测速或当前报价。</p>'''
slides[7]=(slides[7][0].replace('07','08',1),slides[7][1],slides[7][2])
slides[8]=(slides[8][0].replace('08','09',1),slides[8][1],slides[8][2])
slides.insert(7,('07　三种方法的时间与费用',timing,'来源：OpenCV run.json、API实例记录中的152次attempts，以及精修summary.json。所有attempts均有total_seconds。时间口径不同，不计算速度倍数；混合方法复用同一批API初稿。'))
css+='''.cost-table{font-size:20px;min-width:850px}.cost-table th,.cost-table td{vertical-align:top;padding:18px 12px}.cost-table tbody th{color:#17313d;font-size:21px}'''
css+='''.class-scroll{overflow-x:auto}.class-stats{font-size:20px;min-width:760px}.class-stats td,.class-stats th{padding:13px 12px;vertical-align:top}.class-stats tbody th{font-size:20px;color:#17313d}.class-secondary{font-size:16px;color:#62747b}.leading-iou{font-weight:700;color:#10796e}.class-stats small{font-size:15px;color:#62747b}.class-stats th:first-child{min-width:155px}'''
body=''.join(f'<section class="slide" data-title="{html.escape(t.replace("<br>"," "),quote=True)}" data-note="{html.escape(n or "本页为已保存实验结果的精简总结。",quote=True)}"><h1>{t}</h1>{b}<footer>{i+1:02d} / {len(slides):02d}</footer></section>' for i,(t,b,n) in enumerate(slides))
controls='<nav id="controls"><button id="prev">← 上一节</button><span id="count"></span><button id="next">下一节 →</button><select id="jump" aria-label="目录"></select><button id="noteButton">备注</button><button id="full">全屏</button><button id="print">打印</button></nav><div id="progress"></div><aside id="notes"></aside><dialog></dialog>'
doc='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>外立面缺陷分割实验 · 精简回顾</title><style>'+css+'</style></head><body><main>'+body+'</main>'+controls+'<script>'+JS+'</script></body></html>'
(OUT/'index.html').write_text(doc,encoding='utf8')
print('Built',len(slides),'sections,',len(doc.encode('utf8')),'bytes:',OUT/'index.html')
