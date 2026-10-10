"""Readable method diagrams with key branches, without implementation parameters."""
import html,base64,re
class Diagram:
 def __init__(self,title,height):
  self.p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="{height}" viewBox="0 0 1040 {height}"><title>{title}</title><defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#52766f"/></marker></defs><rect width="1040" height="{height}" fill="#faf9f5"/>']
 def text(self,x,y,t,size=19,bold=False):self.p.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Microsoft YaHei,sans-serif" font-size="{size}" font-weight="{600 if bold else 400}" fill="#17313d">{html.escape(t)}</text>')
 def box(self,x,y,w,title,desc,fill='#fff'):
  self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="94" rx="9" fill="{fill}" stroke="#84a89e" stroke-width="1.5"/>')
  self.text(x+w/2,y+34,title,23,True)
  for i,t in enumerate(desc.split('|')):self.text(x+w/2,y+62+i*23,t,18)
 def arrow(self,path):self.p.append(f'<path d="{path}" fill="none" stroke="#52766f" stroke-width="2" marker-end="url(#a)"/>')
 def svg(self):return ''.join(self.p)+'</svg>'

def diagrams():
 d=Diagram('OpenCV：按类型选择处理方法',840)
 d.box(230,15,580,'输入原图、检测框与缺陷类型','同一张图中的每个缺陷单独处理','#e0f0eb')
 d.arrow('M520 109 V142');d.box(230,145,580,'取出检测框内的局部区域','缩小处理范围，记录在原图中的位置')
 for x in [180,520,860]:d.arrow(f'M520 239 V268 H{x} V300')
 d.box(20,303,320,'裂缝／网裂','突出细暗线|筛选连续的线状区域')
 d.box(360,303,320,'锈迹／污渍等','按颜色与明暗差异|筛选疑似缺陷像素')
 d.box(700,303,320,'剥落／破损','按颜色分组建立初选区域|再区分前景与背景')
 for x in [180,520,860]:d.arrow(f'M{x} 397 V428 H520 V462')
 d.box(230,465,580,'清理候选区域','去掉小噪点，按方法整理连通区域')
 d.arrow('M520 559 V591');d.box(230,594,580,'还原到原图位置与尺寸','保留独立实例，再合并为整图mask')
 d.arrow('M520 688 V720');d.box(230,723,580,'输出mask与叠加图','用于逐图检查和量化比较','#e0f0eb')
 result=[('opencv',d.svg())]
 d=Diagram('image2.5：局部输入与原图还原',825)
 rows=[('输入原图、检测框与缺陷类型','使用固定检测结果，不重新检测','统一输入，便于公平比较'),('裁出目标及周围墙面','保留少量上下文，记录裁剪位置','看清缺陷，也保留背景参照'),('整理成模型输入画布','细长区域分段排列，记录缩放与拼接关系','避免细长缺陷被缩得过小'),('调用API生成黑白mask','每个缺陷单独请求，提示目标类型与位置','白色是缺陷，黑色是背景'),('解码并还原到原图','二值化、拆回各段、恢复尺寸并放回坐标','坐标还原不能消除模型画偏'),('输出实例mask、整图mask与叠加图','同时记录耗时、token、费用和失败状态','失败项后续单独重试')]
 for i,(t,desc,why) in enumerate(rows):
  y=15+i*135;d.box(20,y,660,t,desc,'#e0f0eb' if i in (0,5) else '#fff')
  d.text(860,y+35,'目的／注意',18,True);d.text(860,y+65,why,18)
  if i<5:d.arrow(f'M350 {y+94} V{y+132}')
 result.append(('image25',d.svg()))
 d=Diagram('API加OpenCV：精修、检查与回退',925)
 d.box(220,15,600,'输入API初稿＋原图＋检测框／类型','保留原mask，作为精修依据和回退版本','#e0f0eb')
 d.arrow('M520 109 V143');d.box(220,146,600,'限定调整范围','围绕已有mask，在原图像素上寻找更合适的区域')
 for x in [270,770]:d.arrow(f'M520 240 V269 H{x} V302')
 d.box(50,305,440,'裂缝类：寻找细暗线','调整线状区域，尽量贴合裂缝')
 d.box(550,305,440,'区域类：区分前景与背景','用API初稿引导区域分割')
 for x in [270,770]:d.arrow(f'M{x} 399 V429 H520 V459')
 d.box(180,462,680,'候选结果是否出现异常？','空mask／面积比＜0.35或＞2.50／与初稿IoU＜0.10','#fff0d6')
 d.arrow('M520 556 V581 H270 V622');d.arrow('M520 556 V581 H770 V622')
 d.text(270,609,'未触发异常',18);d.text(770,609,'异常或求解失败',18)
 d.box(50,625,440,'采用精修候选','作为该实例的最终mask','#e0f0eb')
 d.box(550,625,440,'回退API初稿','保留原结果，记录回退原因','#f9e9e2')
 for x in [270,770]:d.arrow(f'M{x} 719 V748 H520 V777')
 d.box(220,780,600,'输出最终mask与叠加图','原稿、候选与最终版本分别保存','#e0f0eb')
 d.text(520,909,'异常检查不是质量验收；被采用的精修结果仍可能退化。',18)
 result.append(('hybrid',d.svg()))
 return result

def attach(slides,out):
 assets=out/'flows';assets.mkdir(exist_ok=True);figures=[]
 for key,svg in diagrams():
  (assets/(key+'.svg')).write_text(svg,encoding='utf8')
  src='data:image/svg+xml;base64,'+base64.b64encode(svg.encode('utf8')).decode()
  summary={
   'opencv':'根据缺陷类型，在检测框内用颜色、明暗和纹理规则直接筛选缺陷像素，生成mask。',
   'image25':'将缺陷附近的局部图像和类型提示交给图像模型生成mask，再按记录的坐标放回原图。',
   'hybrid':'以API生成的mask为初稿，结合原图像素进行局部精修，若候选结果触发异常规则则保留初稿。',
  }[key]
  figure=f'<p class="method-summary"><b>一句话理解：</b>{summary}</p><figure class="brief-flow"><img src="{src}" alt="{key}处理流程：输入、分支与输出"><figcaption>点击可放大、缩放和拖动查看</figcaption></figure>'
  if key=='image25':figure+=prompt_description()
  if key=='hybrid':figure+=threshold_description()
  figures.append(figure)
 title,body,note=slides[3];counter=iter(figures)
 body=re.sub(r'<p class="route">.*?</p>',lambda m:next(counter),body)
 slides[3]=(title,body,'补充主要数据流、类别分支、坐标还原与异常回退，省略具体参数和代码。')
CSS='''.brief-flow{margin:14px 0 20px}.brief-flow img{display:block;width:100%;height:auto;background:none;cursor:zoom-in}.brief-flow figcaption{text-align:right;font-size:15px;margin:0;color:#62747b}.method{padding:16px 0 28px}.method>p{font-size:21px;margin:8px 0 18px}@media(max-width:760px){.brief-flow{overflow-x:auto}.brief-flow img{width:900px;max-width:none}.brief-flow figcaption{text-align:left}}'''

def prompt_description():
 template='''Return only a black/white binary mask of this EXACT 1024x1024 input canvas. White=specified visible defect, black=background. This canvas contains {panel_count} separate photo panels in reading order. Process each panel IN PLACE independently; do not combine, move, resize, extend or reconnect panels. All magenta padding MUST be black. Target class: {class_code} {class_description}. Target region coordinates on this submitted canvas: {target_bbox_canvas_list}. Follow actual visible defect boundaries; never fill rectangles. {optional_faint_tail}Do not select intact light wall, shadows or padding. No labels, margins, illustrations or text. Target ID: {target_id}. {optional_subtype_instruction}'''
 return '''<h3>实际使用的 Prompt</h3><p>提示词要求：只返回黑白mask，按指定类型和位置选出可见缺陷；保持各局部面板的位置与形状，不把检测框直接填白，也不选中完好墙面、阴影或填充区。</p><details class="prompt-detail"><summary>展开英文提示词模板与动态字段</summary><pre>'''+html.escape(template)+'''</pre><p>上方是代码拼接逻辑的模板化展示，花括号会被每次请求的实际值替换，不是原样发送。</p><ul><li><code>panel_count</code>：画布中局部面板的数量；<code>target_bbox_canvas_list</code>：目标在上传画布中的坐标，不是原图坐标。</li><li><code>class_code / class_description</code>：缺陷类型及英文定义；<code>target_id</code>：实例编号。例如裂缝C使用 <code>visible linear crack at actual width; exclude joints and shadows</code>。</li><li><code>optional_faint_tail</code>：仅R、T、L类保留 <code>Keep faint tail only where visibly discolored. </code>，其他类不添加。</li><li><code>optional_subtype_instruction</code>：地面垃圾增加 <code>Select ground litter: discarded cloth, bags, masks, hangers and loose rubbish; exclude ground stains and wall dirt.</code>；墙面污渍增加 <code>Select wall staining only; exclude ground litter, shadows and intact wall.</code>；未指定这两种子类型时不添加。</li></ul><p class="muted">依据 local_crop_trial.py 与 batch_local.py 的提示词拼接逻辑整理，并核对已保存的 geometry.json 请求记录。提示词约束不能保证生成轮廓完全对齐。</p></details>'''

def threshold_description():
 return '''<h3>候选结果异常：如何判断？</h3><p>以API原mask为比较对象，以下任一条件触发时，回退到原API结果。</p><table class="thresholds"><thead><tr><th>检查项</th><th>触发回退的条件</th></tr></thead><tbody><tr><td>空结果</td><td>候选mask没有任何前景像素。</td></tr><tr><td>面积变化过大</td><td>候选面积 ÷ API原mask面积 <b>&lt; 0.35</b> 或 <b>&gt; 2.50</b>。</td></tr><tr><td>与初稿分歧过大</td><td>候选mask与API原mask的 <b>IoU &lt; 0.10</b>。</td></tr><tr><td>求解失败</td><td>精修求解出现异常，例如有效前景／背景种子不足。</td></tr></tbody></table><p class="muted">面积比恰好为0.35或2.50、IoU恰好为0.10时，不触发对应回退条件。若API原mask本身为空，直接保留空初稿，不进入精修。</p><p><b>注意：</b>这里的IoU比较“候选与API初稿”，不是与参考标注比较。阈值是本次程序的保护规则，不是质量合格线，也不是已验证的最优参数。裂缝对齐等人工复核提示不单独触发回退。</p>'''

CSS+='''.prompt-detail{margin:18px 0;padding:18px 22px;border:1px solid #ccd6d1}.prompt-detail summary{cursor:pointer;font-size:21px;font-weight:600;color:#10796e}.prompt-detail pre{white-space:pre-wrap;overflow-wrap:anywhere;font:17px/1.7 Consolas,monospace;background:#eef2ee;padding:18px}.prompt-detail p,.prompt-detail li{font-size:19px;line-height:1.8}.prompt-detail li{margin:12px 0}code{overflow-wrap:anywhere}.thresholds{font-size:20px}.thresholds th{font-size:19px}.thresholds td{vertical-align:top}@media print{details::details-content{display:block}.prompt-detail pre{font-size:14px}}'''
CSS+='''.method>.method-summary{border-left:4px solid #10796e;padding:10px 0 10px 18px;margin:16px 0 22px;font-size:23px;color:#17313d}'''
