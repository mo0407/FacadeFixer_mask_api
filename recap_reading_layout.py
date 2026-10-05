"""Scrollable experiment presentation and accessible, zoomable image viewer."""
def configure(slides, asset, report):
    slides[:] = [s for s in slides if s['kind'] != 'appendix']
    api = next(s for s in slides if s['title'].startswith('方法二'))
    api['title'] = '方法二：让模型一次只处理一个缺陷，再把mask放回原图'
    api['body'] = '''<p class="takeaway">输入是原图＋已确定的bbox＋缺陷类型。bbox只告诉模型“在哪里找”，不能直接当作缺陷轮廓。</p>
    <h3>为什么不直接把整张图交给模型？</h3>
    <p>整图中的缺陷可能很小，而且一张图可能有多个缺陷。当前程序按bbox逐个处理，让目标在输入中更清楚，也方便把每次结果对应到实例ID。这里使用的是图像生成接口，仍可能重绘或移动轮廓；局部裁剪只能减轻问题，不能保证像素对齐。</p>
    <ol class="steps">
    <li><b>从原图裁出目标和少量周围环境。</b><p>按bbox外扩后裁图：左右各增加bbox宽度的20%，上下各增加高度的2.5%，每侧至少12像素，遇到原图边缘则截断。保留周围墙面，是为了让模型区分缺陷与正常背景。同时记录裁图在原图中的左上角坐标。</p></li>
    <li><b>把局部图装进1024×1024的输入画布。</b><p>普通局部图用一个面板；宽高比超过3的细长局部图，沿长边切成4段，排成2×2。这样细裂缝不用整条挤进一个方形，能保留更多局部细节。代价是切段打断整体连续性，拼回时也可能出现接缝。画布空白处使用洋红色，与黑白mask区分。</p></li>
    <li><b>发送一次请求，让API输出黑白mask。</b><p>发送局部图画布、目标位置和缺陷类型。提示模型用白色表示目标缺陷、黑色表示背景。每个bbox单独请求：因此50张图对应109个实例任务，并不只有50次请求；失败重试会增加次数。</p></li>
    <li><b>把返回图变成二值mask，并按记录“拆回去”。</b><p>灰度阈值128区分黑白；返回图若长宽比明显异常则拒收。按保存的面板位置取出mask，把各面板用最近邻缩放还原为原局部尺寸，再按切段顺序拼回。最近邻避免插值产生灰色边缘。</p></li>
    <li><b>放回原图对应位置，保存每个实例。</b><p>先创建一张与原图同宽高的全黑图，再按第一步记录的坐标把局部mask放进去，最后限制在原bbox内。各实例分别保存，也合并成整图mask；将mask着色叠到原图上，便于检查。</p></li>
    </ol>
    <h3>“放回原图”不等于“自动纠正偏移”</h3>
    <p>例如裁图起点是原图的(100,200)，还原后的局部点(20,30)就放到原图(120,230)。程序能保证坐标变换一致；如果模型把裂缝画到了局部图的错误位置，这个错误也会一起被放回去。方法三才是在原图像素上进一步精修。</p>
    <p class="foot">这里的边距、切段阈值和1024画布是当前实现的工程选择，尚未通过消融实验证明为最佳参数。bbox外的漏检不由本步骤补充。</p>'''
    for prefix,key in [('方法一','opencv'),('方法二','image25'),('方法三','hybrid')]:
        s=next(s for s in slides if s['title'].startswith(prefix))
        s['kind']='method-page'
        s['body']='<div class="method-layout"><div>'+s['body']+'</div><figure class="method-flow"><figcaption>对应的详细处理流程 · 点击放大，可缩放与拖动</figcaption><img class="zoom" src="'+asset(report/'flows'/(key+'.svg'))+'" alt="'+s['title']+'详细流程图"></figure></div>'

CSS = '''
html,body{height:auto;min-height:100%;overflow:auto;background:#e6eae7;scroll-behavior:smooth}
#viewport{position:static;display:block;padding:28px 24px 95px}
#stage{width:min(1600px,100%);height:auto;margin:auto;transform:none!important;box-shadow:none;background:none}
.slide,.slide.active{position:relative;display:block;inset:auto;min-height:820px;height:auto;margin:0 0 30px;padding:60px 65px 80px;overflow:visible;background:#f8f7f2;scroll-margin-top:20px;box-shadow:0 8px 30px #17313d12}
.slide h1{font-size:44px;max-width:none}.content{font-size:25px}.content h3{margin-top:26px}.slide footer{left:65px;right:65px}.cover{min-height:900px}.cover h1{max-width:950px}.cover-image{width:30%;right:45px}.cover-copy{max-width:65%}
.method-layout{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:45px;align-items:start}
.method-layout table{font-size:21px}.method-layout th{font-size:20px}.method-layout td{min-width:0}.method-layout .chain{grid-template-columns:1fr;gap:16px}.method-layout .chain>div:after{display:none}.method-layout .chain p{margin:5px 0}.method-layout .columns{grid-template-columns:1fr;gap:10px}
.method-flow{margin:0;position:sticky;top:20px}.method-flow figcaption{font-size:19px;color:#62747b;margin-bottom:14px}.method-flow img{width:100%;height:auto;background:white;display:block}.steps{padding-left:28px}.steps li{padding-left:8px;margin:28px 0}.steps p{margin:10px 0!important}.method-layout .takeaway{margin-top:0!important;font-size:26px}
#controls{position:fixed;z-index:10;flex-wrap:wrap;height:auto;min-height:60px;padding:8px}#progress{position:fixed;z-index:11}#notes{z-index:12}
dialog{width:96vw;height:94vh;max-width:96vw;max-height:94vh;padding:0;overflow:hidden;background:#17232c;color:white}
.viewer-tools{height:60px;display:flex;gap:12px;align-items:center;padding:8px 18px}.viewer-tools button{display:inline-block;margin:0}.viewer-tools #close{margin-left:auto}.viewer-tools span{font-size:16px}
.viewer-canvas{height:calc(100% - 60px);width:100%;overflow:auto;touch-action:none;cursor:grab;background:#d6ddda}.viewer-canvas.dragging{cursor:grabbing}dialog .viewer-canvas img{max-width:none;max-height:none;display:block;object-fit:contain;user-select:none;margin:auto}
@media(max-width:1000px){.method-layout,.columns{grid-template-columns:1fr}.method-flow{position:static}.slide{padding:30px 25px 70px}.slide h1{font-size:32px}.content{font-size:21px}.cover h1{font-size:40px}.case{grid-template-columns:1fr 1fr}.cover-image{position:static;width:100%;height:300px}.cover-copy{max-width:100%}table{font-size:18px}.chain{grid-template-columns:1fr}.chain>div:after{display:none}.slide footer{left:25px;right:25px}.viewer-tools{gap:5px;padding:5px}.viewer-tools span{display:none}}
@media print{@page{size:A3 landscape;margin:12mm}html,body{background:white}#viewport{padding:0}#stage{width:100%}.slide{width:100%;height:auto;min-height:0;break-after:page;box-shadow:none;margin:0;padding:20px 20px 65px}.method-flow{position:static}.method-layout{grid-template-columns:1fr 1fr}#controls,#progress,#notes,dialog{display:none!important}}
'''

JS = '''
const slides=[...document.querySelectorAll('.slide')],sel=document.querySelector('#jump');let index=0;
slides.forEach((s,i)=>{s.id='slide-'+(i+1);let o=document.createElement('option');o.value=i;o.textContent=`${i+1}. ${s.dataset.title}`;sel.append(o)});
function update(n){index=n;sel.value=n;document.querySelector('#count').textContent=`${n+1} / ${slides.length}`;document.querySelector('#notes').textContent=slides[n].dataset.note;document.querySelector('#progress').style.width=((n+1)/slides.length*100)+'%'}
function go(n){n=Math.max(0,Math.min(slides.length-1,n));update(n);slides[n].scrollIntoView({behavior:'instant',block:'start'});history.replaceState(null,'','#slide-'+(n+1))}
let scheduled=false;window.addEventListener('scroll',()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{let n=0;slides.forEach((s,i)=>{if(s.getBoundingClientRect().top<innerHeight*.38)n=i});update(n);scheduled=false})});
document.querySelector('#prev').onclick=()=>go(index-1);document.querySelector('#next').onclick=()=>go(index+1);sel.onchange=()=>go(+sel.value);
document.querySelector('#noteButton').onclick=()=>document.querySelector('#notes').classList.toggle('show');
document.querySelector('#print').onclick=()=>window.print();document.querySelector('#full').onclick=async()=>{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen()};
const dialog=document.querySelector('dialog');dialog.innerHTML='<div class="viewer-tools"><button id="zoomOut" aria-label="缩小">−</button><button id="zoomIn" aria-label="放大">＋</button><button id="fit">适合窗口</button><button id="actual">原始大小</button><span id="zoomLevel"></span><span>滚轮缩放 · 拖动查看</span><button id="close">关闭 Esc</button></div><div class="viewer-canvas"><img alt="放大图片" draggable="false"></div>';
const canvas=dialog.querySelector('.viewer-canvas'),large=canvas.querySelector('img');let zoom=1,baseW=1,baseH=1;
function scale(z){zoom=Math.max(.1,Math.min(12,z));large.style.width=(baseW*zoom)+'px';large.style.height=(baseH*zoom)+'px';document.querySelector('#zoomLevel').textContent=Math.round(zoom*100)+'%'}
function fit(){scale(Math.min(canvas.clientWidth/baseW,canvas.clientHeight/baseH)*.96);canvas.scrollTo(0,0)}
document.querySelectorAll('.slide img').forEach(im=>{im.tabIndex=0;im.setAttribute('role','button');im.style.cursor='zoom-in';im.onclick=()=>{large.onload=()=>{baseW=large.naturalWidth||1600;baseH=large.naturalHeight||1200;fit()};large.alt=im.alt;dialog.showModal();large.src=im.src;if(large.complete&&large.naturalWidth)large.onload()};im.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();im.click()}}});
document.querySelector('#close').onclick=()=>dialog.close();document.querySelector('#zoomIn').onclick=()=>scale(zoom*1.4);document.querySelector('#zoomOut').onclick=()=>scale(zoom/1.4);document.querySelector('#fit').onclick=fit;document.querySelector('#actual').onclick=()=>scale(1);
canvas.addEventListener('wheel',e=>{e.preventDefault();let x=(canvas.scrollLeft+e.offsetX)/zoom,y=(canvas.scrollTop+e.offsetY)/zoom;scale(zoom*(e.deltaY<0?1.15:1/1.15));canvas.scrollLeft=x*zoom-e.offsetX;canvas.scrollTop=y*zoom-e.offsetY},{passive:false});
let drag=null;canvas.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,l:canvas.scrollLeft,t:canvas.scrollTop};canvas.setPointerCapture(e.pointerId);canvas.classList.add('dragging')};canvas.onpointermove=e=>{if(drag){canvas.scrollLeft=drag.l+drag.x-e.clientX;canvas.scrollTop=drag.t+drag.y-e.clientY}};canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;canvas.classList.remove('dragging')};
document.addEventListener('keydown',e=>{if(dialog.open||['SELECT','INPUT','TEXTAREA'].includes(document.activeElement.tagName))return;if(e.key==='ArrowRight'){e.preventDefault();go(index+1)}if(e.key==='ArrowLeft'){e.preventDefault();go(index-1)}if(e.key.toLowerCase()==='n')document.querySelector('#noteButton').click()});
update(0);if(location.hash.startsWith('#slide-'))requestAnimationFrame(()=>go((+location.hash.replace('#slide-','')||1)-1));
'''
