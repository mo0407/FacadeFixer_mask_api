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
 d.box(220,462,600,'候选结果是否出现异常？','检查空mask、面积变化和与初稿的重合程度','#fff0d6')
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
  figures.append(f'<figure class="brief-flow"><img src="{src}" alt="{key}处理流程：输入、分支与输出"><figcaption>点击可放大、缩放和拖动查看</figcaption></figure>')
 title,body,note=slides[3];counter=iter(figures)
 body=re.sub(r'<p class="route">.*?</p>',lambda m:next(counter),body)
 slides[3]=(title,body,'补充主要数据流、类别分支、坐标还原与异常回退，省略具体参数和代码。')
CSS='''.brief-flow{margin:14px 0 20px}.brief-flow img{display:block;width:100%;height:auto;background:none;cursor:zoom-in}.brief-flow figcaption{text-align:right;font-size:15px;margin:0;color:#62747b}.method{padding:16px 0 28px}.method>p{font-size:21px;margin:8px 0 18px}@media(max-width:760px){.brief-flow{overflow-x:auto}.brief-flow img{width:900px;max-width:none}.brief-flow figcaption{text-align:left}}'''
