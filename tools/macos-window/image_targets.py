"""Bounded, cached local image matching using NumPy; no model or UI access."""
from pathlib import Path
import numpy as np
from PIL import Image

def pixels(image, mode):
    a=np.asarray(image.convert('RGB'),dtype=np.float32)
    if mode=='white-glyph':return ((a.min(axis=2)>180)&((a.max(axis=2)-a.min(axis=2))<95)).astype(np.float32)
    return a.mean(axis=2)

def match(observation, spec):
    config=observation.ocr_config or {}
    filename=config.get('templates',{}).get(spec['template'])
    if not filename:raise RuntimeError('Missing configured image template: '+spec['template'])
    bounds=spec['bounds'];mode=spec.get('mode','white-glyph')
    key=('template',str(filename),*bounds,mode)
    if key not in observation.timer_regions:
        with Image.open(observation.image_path) as source:
            source=pixels(source.crop(bounds),mode)
        with Image.open(Path(filename)) as template:template=pixels(template,mode)
        h,w=source.shape;th,tw=template.shape
        if not (3<=th<=h and 3<=tw<=w):raise RuntimeError('Template does not fit search region')
        n=th*tw;centered=template-template.mean();norm=float((centered*centered).sum())
        if norm<=1e-8:raise RuntimeError('Uniform image template is ambiguous')
        shape=(h+th-1,w+tw-1)
        corr=np.fft.irfft2(np.fft.rfft2(source,shape)*np.fft.rfft2(centered[::-1,::-1],shape),shape)[th-1:h,tw-1:w]
        def sums(a):
            integral=np.pad(a,((1,0),(1,0))).cumsum(0).cumsum(1)
            return integral[th:,tw:]-integral[:-th,tw:]-integral[th:,:-tw]+integral[:-th,:-tw]
        variance=np.maximum(sums(source*source)-sums(source)**2/n,0)
        denominator=np.sqrt(variance*norm)
        scores=np.divide(corr,denominator,out=np.full_like(corr,-1.),where=denominator>1e-5)
        index=np.unravel_index(np.argmax(scores),scores.shape);score=float(np.clip(scores[index],-1,1))
        point=[round(bounds[0]+index[1]+tw/2),round(bounds[1]+index[0]+th/2)]
        observation.timer_regions[key]={'score':score,'point':point}
    result=observation.timer_regions[key]
    observation.visual_checks.append({'template':spec['template'],'bounds':bounds,**result})
    return result
