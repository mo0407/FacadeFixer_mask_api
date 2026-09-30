"""Build standalone SVG flow diagrams and GitHub Mermaid source from code-reviewed steps."""
from pathlib import Path
from html import escape
import json
from PIL import ImageFont,Image,ImageDraw
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'comparison50_three_methods_v1'
COLORS={'input':('#e0f2fe','#0284c7'),'process':('#f1f5f9','#475569'),'decision':('#fef3c7','#d97706'),'artifact':('#dcfce7','#16a34a'),'error':('#fee2e2','#dc2626')}
def node(id,x,y,w,h,title,lines,kind='process'):return dict(id=id,x=x,y=y,w=w,h=h,title=title,lines=lines,kind=kind)
def edge(a,b,label='',via=None,dash=False):return dict(a=a,b=b,label=label,via=via,dash=dash)
flows=[]
nodes=[
 node('i',440,80,920,130,'01 输入：只读原图 + 冻结检测清单',['原图 I：H×W×3 RGB；每张可有多个实例','每实例：ID、类别/子类型、bbox=[x1,y1,x2,y2)，坐标为原图像素','不读取 API mask、参考 mask 或人工逐图轮廓'],'input'),
 node('c',440,260,920,120,'02 逐实例裁剪与计算尺度',['ROI = I[y1:y2, x1:x2]；记录原始 ROI 宽高、偏移与缩放','裂缝 C/M：原分辨率；其他类：ROI 长边最多 1000 像素','由类别分流；下方六条分支只执行对应的一条']),
 node('a',20,470,275,230,'03A 裂缝 C / 网裂 M',['RGB → 灰度 → Gaussian 平滑','多尺度 black-hat 取最大响应','响应阈值：Otsu×0.65，限7–30','另约束灰度 < 第80百分位','连通域及线形过滤','不做破坏细线的大开运算']),
 node('b',315,470,275,230,'03B 锈迹 T / 腐蚀 R',['RGB → HSV 和 Lab','筛红、橙、棕色像素','H<27 或 H>173；S>48','V>28；Lab a>127、b>132','去小连通域，填少量小孔','颜色不能独立证明锈蚀语义']),
 node('d',610,470,275,230,'03C 植物 V',['RGB → HSV + 灰度','绿色条件：H 29–100','S>38 且 V>28','另取暗色：灰度 < 截断Otsu','绿色 ∪ 暗色 → 连通域过滤','阴影可能混入']),
 node('e',905,470,275,230,'03D 地面垃圾 D',['子类型必须是 GroundLitter','低灰度样本的 Lab 中位数','作为地面背景色','取较亮像素或高色度/色差','亮度分位阈值 + Lab 距离','去小连通域；暗色布料可漏']),
 node('f',1200,470,275,230,'03E 污渍 D / 渗漏 L',['RGB → 灰度及局部平滑','暗色 Otsu + 局部亮度残差','候选：全局暗 或 局部偏暗','L 额外加入黄棕色条件','去小连通域、填小孔','白色析出物仍可能漏选']),
 node('g',1495,470,285,230,'03F 剥落 P / 破损 S',['RGB → Lab → 4类聚类','bbox边缘主色估计完好背景','色差选择前景簇 → 种子','腐蚀内核=确定前景','边缘非目标=确定背景','GrabCut 3轮 → 清理与填小孔']),
 node('merge',440,800,920,130,'04 输出 ROI 二值候选，保留方法与参数',['每条分支产生当前 ROI 大小的 0/1 mask','P/S：GrabCut失败或种子不足时使用聚类种子并记录原因','记录尺度、阈值、前景比例和可能的阴影/材质误判'],'artifact'),
 node('restore',440,980,920,120,'05 还原到原图坐标',['若ROI缩小过：最近邻恢复到原bbox宽高','建立全黑 H×W 画布，在 [x1:x2, y1:y2] 对应位置贴回','每个实例单独保存，不把不同bbox合成一个实例']),
 node('export',440,1160,920,150,'06 聚合与导出',['实例 mask_i → 按类并集 → 全部实例并集 M_total','M_total / mask_i 均为 H×W，PNG单通道0/255','原图 + 实例彩色mask + bbox/ID → 叠加图；同时输出bbox图','JSON含类别、bbox、面积、列优先RLE；保存耗时、参数、质量提示'],'artifact'),
 node('verify',440,1360,920,125,'07 结果验证与人工复核',['检查尺寸、二值、bbox范围、实例并集及RLE可逆性','小/空mask、几乎填满bbox等仅触发复核，不代表自动判错','本次109实例全部有文件；不代表109实例分割正确'],'decision')]
edges=[edge('i','c')]+[edge('c',k,'按类别',[(900,410),(nodes[j]['x']+nodes[j]['w']/2,410)]) for j,k in enumerate(['a','b','d','e','f','g'],2)]+[edge(k,'merge','',[(next(n for n in nodes if n['id']==k)['x']+next(n for n in nodes if n['id']==k)['w']/2,750),(900,750)]) for k in ['a','b','d','e','f','g']]+[edge('merge','restore'),edge('restore','export'),edge('export','verify')]
flows.append(('opencv','纯 OpenCV：原图像素规则分割',1800,1540,nodes,edges,'对应 skills/facade-opencv-mask/scripts/segment.py。基线不使用模型mask，亦不使用assisted人工引导。'))
nodes=[
 node('i',70,80,930,115,'01 输入与预检查',['原图 I(H×W×3) + 冻结 bbox/ID/类型/子类型','读取模型配置、环境变量/密钥文件；检查范围与bbox；不重新检测','默认 dry-run：不发请求；--run 才进入付费处理'],'input'),
 node('gate',70,245,930,140,'02 缓存、复用与提交门控',['已有成功记录：验证原图/输出哈希后跳过','已有失败记录：默认跳过；--retry-failed 才在本轮重试一次','首次且00/04历史试验可用：核对bbox/类型并复制、标记 carried_forward','无可用记录 → 当前实例进入裁剪；本次00和04走历史复用'],'decision'),
 node('roi',70,435,930,125,'03 取局部上下文 ROI',['横向边距=max(12, round(bbox宽×20%))','纵向边距=max(12, round(bbox高×2.5%))；ROI裁到原图边界','得到局部RGB及其原图偏移 (a,b)；bbox仍保持冻结']),
 node('tile',70,610,930,140,'04 选择单面板或四段拼图',['max(ROI宽/高, ROI高/宽) > 3？','是：沿长边等分4段，按阅读顺序放入2×2网格（每格512）','否：使用一个1024面板；每面板等比缩放、居中留边','总画布固定1024×1024，洋红补边；图像缩放使用LANCZOS'],'decision'),
 node('geo',1080,610,610,160,'并行产物：geometry.json',['每面板 source_xyxy / canvas_xyxy','scale_xy=(sx,sy) 与画布内目标bbox','前向坐标：u=(x-x0)×sx+ox','v=(y-y0)×sy+oy','这些数据只用于提示和确定性逆映射'],'artifact'),
 node('prompt',70,810,930,125,'05 构造提示并持久化请求输入',['上传PNG画布 + 类型定义 + 实例ID + 画布bbox坐标','要求逐面板原位分割，白=目标，黑=背景/补边；不画框或文字','垃圾/墙面污渍使用独立子类型提示；保存submitted_images与prompt']),
 node('api',70,985,930,125,'06 单实例图像API请求',['POST /v1/images/edits，multipart：PNG + prompt + model','服务商标识 gpt-image-2.5；请求 size=1024x1024、quality=high','接收base64或图片URL；下载并保留原始返回；每bbox一次请求']),
 node('err',1080,985,610,185,'异常支路：失败不伪造mask',['HTTP / SSL / 下载 / 解码失败 → 记录错误','401/403设置停止标记，阻止后续新提交','不进行自动付费重试；需显式 retry-failed','保存attempts、耗时、可获得的usage与费用','缺失实例导致图片partial，不能视为无缺陷'],'error'),
 node('norm',70,1160,930,135,'07 校验返回画布并二值化',['拒绝 |返回宽/高 - 1| > 0.02 的图像，不强行拉伸','透明区域合成到黑底 → 灰度 → 阈值128 → 0/255','最近邻归一到1024×1024；实际返回可不是1024','非方形比例异常也进入失败记录支路']),
 node('back',70,1345,930,140,'08 根据保存的几何信息逆映射',['从归一画布裁出各面板 canvas_xyxy','最近邻还原成 source_xyxy 对应的原图区域大小','按原图坐标贴回全黑 H×W 画布；保存 unclipped mask','此处只还原坐标，不按原图纹理修边；生成内容仍可能错位']),
 node('clip',70,1535,930,110,'09 裁到冻结bbox，保存原尺寸实例mask',['final[y1:y2,x1:x2] = restored[y1:y2,x1:x2]，框外=0','保存mask哈希、空结果标记、框外裁除像素数；空mask也需复核']),
 node('out',70,1695,930,140,'10 聚合、叠加、JSON/RLE和统计',['按实例/类别/全部并集导出；叠加使用原图与mask混合着色','成功记录保留usage、token、API秒数、总秒数和估算费用','token未知记null；失败费用未知不当作0；原始账单未独立核验','本次105/109有mask；00/04复用来源单独记录'],'artifact'),
 node('cache',1080,245,610,140,'沿用分支的输出',['不发起当前实例新请求','已有成功记录 / 合法历史复用 → 聚合','历史复用保留原始输入、几何及mask','不是本轮同条件新盲测'],'artifact'),
 node('records',1080,1695,610,140,'旁路记录 / 不参与分割',['records/*.json：每次attempt状态、usage','geometry/*.json：坐标变换','raw_model_outputs / raw_masks：模型原稿','任何参考mask都不进入API或坐标还原'],'artifact')]
edges=[edge(a,b) for a,b in [('i','gate'),('gate','roi'),('roi','tile'),('tile','prompt'),('prompt','api'),('api','norm'),('norm','back'),('back','clip'),('clip','out')]]
edges += [dict(a='tile',b='geo',label='保存映射',side=True),dict(a='gate',b='cache',label='跳过/复用',side=True),dict(a='api',b='err',label='失败',side=True),dict(a='out',b='records',label='记录',side=True),edge('geo','back','逆映射参数',[(1710,790),(1710,1310),(535,1310)],True),edge('cache','out','沿用到聚合',[(1735,400),(1735,1665),(535,1665)],True)]
flows.append(('image25','image2.5：局部画布 → 模型mask → 原图坐标',1760,1910,nodes,edges,'对应 batch_local.py / local_crop_trial.py / api_adapter.py / run.py。VS Code只负责运行Python，不是分割模型。'))
nodes=[
 node('i',300,80,1100,125,'01 输入：原图 + 冻结目标 + 已有API实例mask',['原图 I(H×W×3)、mask_i(H×W 0/255)、bbox、类别/ID、源文件哈希','只使用这批API输出作为先验；不读取参考真值、人工轮廓','输入缺少API实例 → 保持缺失/partial，不新增分割结果'],'input'),
 node('check',300,255,1100,120,'02 校验并保留原稿',['核对图像哈希、尺寸、二值值域及mask在bbox内','空输入mask：原样回退并记录empty_input','复制原图、原API总mask/叠加图；逐实例原稿单独保存'],'decision'),
 node('band',300,425,1100,140,'03 确定搜索范围和处理尺度',['band=clip(round(bbox短边×2.5%), 4, 32) 原图像素','取bbox外扩band的原图ROI；allowed只允许冻结bbox内部','裂缝C/M不缩小；其他类：ROI长边最多1200，记录scale','outer = 膨胀(API mask, round(band×scale)) ∩ allowed']),
 node('crack',70,635,730,230,'04A 裂缝 C / 网裂 M：在搜索带中找暗线',['ROI RGB → 灰度 → 3×3 Gaussian(σ=0.6)','椭圆核半径2/4/8的black-hat响应，逐像素取最大','仅在outer取样求Otsu阈值，阈值下限4','candidate = outer ∩ (response > threshold)','8邻域连通域，移除面积<3的小孤点','不做大范围闭运算，不依靠参考裂缝定位']),
 node('region',900,635,730,230,'04B 其他类别：API先验初始化 GrabCut',['outer外=确定背景；outer内=可能背景','原API mask内=可能前景；腐蚀内核=确定前景','内核不足5像素：尝试距离变换>1的内部点','前景/背景仍不足 → 异常回退','固定随机种子，GrabCut 4轮；只取outer内前景','与纯OpenCV基线不同：不再按各类别单独颜色阈值']),
 node('restore',300,955,1100,120,'05 候选还原与bbox限制',['若缩小过：最近邻恢复ROI原尺寸，贴回H×W全黑画布','candidate &= 冻结bbox；保存候选mask，不覆盖原API','求解异常时保存与原mask相同的占位候选，并标solver_failed'],'artifact'),
 node('qc',300,1125,1100,150,'06 异常筛选（不是准确率评估）',['计算面积比 r=候选面积/原mask面积，以及候选与原mask的IoU','候选为空，或 r<0.35 / r>2.5，或 IoU<0.10 → 拒绝','这是与API先验的分歧检查；API本身可能错误','语义/裂缝/空腔风险另记复核标签，不单凭标签拒绝'],'decision'),
 node('accept',70,1345,730,125,'07A 通过异常检查',['selected = candidate','标记 refined_candidate；本次93个','通过只代表未触发异常阈值，不保证变好'],'artifact'),
 node('fallback',900,1345,730,125,'07B 触发异常或求解失败',['selected = 原API mask','标记 raw_fallback；本次12个','保留候选/原因，不能把原有错误当作已修复'],'error'),
 node('export',300,1560,1100,150,'08 聚合并保存三份实例结果',['raw_instance_masks：原稿；candidate_instance_masks：候选','instance_masks：最终选用；按类与全图并集 → mask和叠加图','JSON/RLE记录source_mask_sha256、尺度、搜索半径、面积变化','记录opencv_seconds与回退原因；新增API请求/token/费用均为0'],'artifact'),
 node('eval',300,1760,1100,140,'09 单独评估与复核（只读，不反馈调参）',['检查尺寸/二值/bbox/RLE/并集；先确认文件一致性','需要评估时才读取参考mask：实例ID、类型、bbox和原图哈希对齐','输出IoU、Dice、精确率、召回率、2px边界F1；人工看前后叠加','本次区域宏IoU提高，但边界F1下降：不能自动覆盖所有原稿'],'decision')]
edges=[edge('i','check'),edge('check','band'),edge('band','crack','C/M',[(850,600),(435,600)]),edge('band','region','其他类别',[(850,600),(1265,600)]),edge('crack','restore','',[(435,910),(850,910)]),edge('region','restore','',[(1265,910),(850,910)]),edge('restore','qc'),edge('qc','accept','通过',[(850,1310),(435,1310)]),edge('qc','fallback','拒绝/异常',[(850,1310),(1265,1310)]),edge('accept','export','',[(435,1515),(850,1515)]),edge('fallback','export','',[(1265,1515),(850,1515)]),edge('export','eval')]
flows.append(('hybrid','image2.5 + OpenCV：先验约束精修与回退',1700,1970,nodes,edges,'对应 refine_api_masks.py。是可选后处理；与04号此前的人工轮廓辅助精修不同。'))

def svg(title,width,height,nodes,edges):
 ns={n['id']:n for n in nodes};parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img"><title>{escape(title)}</title><defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0 L10 4 L0 8" fill="#64748b"/></marker></defs><rect width="100%" height="100%" fill="white"/><g font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif"><text x="30" y="42" font-size="26" font-weight="bold">{escape(title)}</text>']
 for e in edges:
  a,b=ns[e['a']],ns[e['b']]
  if e.get('side'):points=[(a['x']+a['w'],a['y']+a['h']/2),(b['x'],b['y']+b['h']/2)]
  else:points=[(a['x']+a['w']/2,a['y']+a['h'])]+(e.get('via') or [])+[(b['x']+b['w']/2,b['y'])]
  coords=' '.join(f'{x},{y}' for x,y in points);dash='stroke-dasharray="8 5"' if e.get('dash') else ''
  parts.append(f'<polyline points="{coords}" fill="none" stroke="#64748b" stroke-width="2" {dash} marker-end="url(#arrow)"/>')
  if e['label']:
   x,y=points[-1];parts.append(f'<text x="{x+8}" y="{y-12}" fill="#475569" font-size="15">{escape(e["label"])}</text>')
 for n in nodes:
  fill,stroke=COLORS[n['kind']];parts.append(f'<rect x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
  size,body,gap=fonts(n)
  parts.append(f'<text x="{n["x"]+14}" y="{n["y"]+29}" font-size="{size}" font-weight="bold">{escape(n["title"])}</text>')
  for j,line in enumerate(n['lines']):parts.append(f'<text x="{n["x"]+14}" y="{n["y"]+57+j*gap}" font-size="{body}">{escape(line)}</text>')
 return ''.join(parts)+'</g></svg>'

FONT='C:/Windows/Fonts/msyh.ttc'
def fonts(n):
 size=17 if n['w']<300 else 21;body=15 if n['w']<300 else 18;gap=27 if n['w']<300 else 25
 while ImageFont.truetype(FONT,size).getlength(n['title'])>n['w']-28:size-=1
 while max(ImageFont.truetype(FONT,body).getlength(t) for t in n['lines'])>n['w']-28:body-=1
 if len(n['lines'])>1:gap=min(gap,(n['h']-65)//(len(n['lines'])-1))
 assert body>=12 and size>=14
 assert 57+(len(n['lines'])-1)*gap+5<n['h'],n['id']
 return size,body,gap

def preview(width,height,nodes,edges,path):
 im=Image.new('RGB',(width,height),'white');d=ImageDraw.Draw(im);ns={n['id']:n for n in nodes}
 for e in edges:
  a,b=ns[e['a']],ns[e['b']]
  points=[(a['x']+a['w'],a['y']+a['h']/2),(b['x'],b['y']+b['h']/2)] if e.get('side') else [(a['x']+a['w']/2,a['y']+a['h'])]+(e.get('via') or [])+[(b['x']+b['w']/2,b['y'])]
  d.line(points,fill='#64748b',width=2)
 for n in nodes:
  fill,stroke=COLORS[n['kind']];d.rounded_rectangle((n['x'],n['y'],n['x']+n['w'],n['y']+n['h']),radius=12,fill=fill,outline=stroke,width=2);size,body,gap=fonts(n)
  d.text((n['x']+14,n['y']+8),n['title'],font=ImageFont.truetype(FONT,size),fill='#172033')
  for j,t in enumerate(n['lines']):d.text((n['x']+14,n['y']+37+j*gap),t,font=ImageFont.truetype(FONT,body),fill='#172033')
 im.save(path)

def main():
 target=OUT/'flows';target.mkdir(exist_ok=True);sections=[];md=['# 三种mask生成方法：处理流程与数据流','','依据当前实现绘制；参考标注只在评估阶段使用。蓝=输入，灰=处理，黄=判断，绿=数据产物，红=异常/回退。']
 for key,title,w,h,nodes,edges,note in flows:
  (target/f'{key}.svg').write_text(svg(title,w,h,nodes,edges),encoding='utf-8')
  preview(w,h,nodes,edges,target/f'{key}_preview.png')
  sections.append(f'<section id="{key}"><h2>{title}</h2><p>{escape(edges and next(f[6] for f in flows if f[0]==key))}</p><p><a href="flows/{key}.svg" target="_blank">原尺寸打开 / 保存 SVG</a></p><div class="diagram"><img src="flows/{key}.svg" alt="{title}"></div></section>')
  md+=['',f'## {title}','',next(f[6] for f in flows if f[0]==key),'','```mermaid','flowchart TD']
  for n in nodes:
   label='<br/>'.join([n['title'],*n['lines']]).replace('"','&quot;');md.append(f'  {n["id"]}["{label}"]')
  for e in edges:md.append(f'  {e["a"]} '+('-.->' if e.get('dash') else '-->')+(f'|"{e["label"]}"|' if e['label'] else '')+f' {e["b"]}')
  md+=['```']
 page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>三种mask方法详细处理流程</title><style>body{font:17px system-ui,"Microsoft YaHei";color:#172033;background:#f4f7fb;margin:0}main{max-width:1500px;margin:auto;padding:28px}nav{position:sticky;top:0;background:white;padding:16px;border-bottom:1px solid #ddd}a{color:#0369a1;margin-right:20px}section{margin:30px 0;background:white;padding:24px;border-radius:14px;scroll-margin-top:70px}.diagram{overflow:auto;border:1px solid #e2e8f0}.diagram img{width:100%;min-width:1200px;height:auto}p{line-height:1.7}@media print{nav{position:static}section{break-before:page}.diagram img{min-width:0}}</style><main><h1>三种 mask 方法：详细处理流程与数据流</h1><p>按当前代码梳理，包含实际输入、尺度变换、类别分支、失败与回退、文件产物。蓝色为输入，灰色为处理，黄色为判断，绿色为数据产物，红色为异常或回退。可横向滚动，或点击SVG原尺寸查看和下载。</p><nav><a href="#opencv">① OpenCV</a><a href="#image25">② image2.5</a><a href="#hybrid">③ image2.5＋OpenCV</a><a href="comparison.html">返回结果对比</a></nav>'''+''.join(sections)+'</main></html>'
 (OUT/'workflows.html').write_text(page,encoding='utf-8');(ROOT/'WORKFLOWS.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
 link='<p class="workflow-link"><a href="workflows.html">查看三种方法的详细处理流程图（输入、数据流、处理及异常分支）</a></p>'
 for path in [OUT/'comparison.html',ROOT/'MASK_METHODS.html']:
  s=path.read_text(encoding='utf-8')
  if 'class="workflow-link"' not in s:s=s.replace('<section id="mask-methods">','<section id="mask-methods">'+link)
  path.write_text(s,encoding='utf-8')
 print('Built 3 SVG diagrams, workflows.html, Mermaid documentation, and report navigation.')
if __name__=='__main__':main()
