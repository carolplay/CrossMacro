"""Explicit, fixed-size calibration; never adapts to an unapproved live resize."""
def calibration(config, reference):
    c=config.get('viewport_calibration')
    if c is None:return None
    if not isinstance(c,dict) or c.get('reference_size')!=reference or not c.get('id'):
        raise ValueError('Invalid fixed viewport calibration')
    native=c.get('native_size');chrome=c.get('titlebar_height')
    if not isinstance(native,list) or len(native)!=2 or any(type(v)is not int or v<=0 for v in native):raise ValueError('Invalid native viewport dimensions')
    if type(chrome)is not int or not 0<=chrome<min(native[1],reference[1]):raise ValueError('Invalid titlebar calibration')
    sx=native[0]/reference[0];sy=(native[1]-chrome)/(reference[1]-chrome)
    if not .9<=sx<=1.1 or not .9<=sy<=1.1 or abs(sx-sy)>.005:raise ValueError('Viewport calibration needs new layout validation')
    return c

def point(config, value, reference):
    c=calibration(config,reference)
    if c is None:return value
    w,h=c['native_size'];rw,rh=reference;t=c['titlebar_height'];x,y=value
    return [round(x*w/rw),round(y if y<t else t+(y-t)*(h-t)/(rh-t))]

def normalize_frame(path,c):
    from PIL import Image
    native=path.with_name(path.stem+'-native'+path.suffix)
    path.rename(native)
    w,h=c['reference_size'];t=c['titlebar_height']
    with Image.open(native) as source:
        source=source.convert('RGB');canvas=Image.new('RGB',(w,h))
        if t:canvas.paste(source.crop((0,0,source.width,t)).resize((w,t),Image.Resampling.LANCZOS),(0,0))
        canvas.paste(source.crop((0,t,source.width,source.height)).resize((w,h-t),Image.Resampling.LANCZOS),(0,t));canvas.save(path)
