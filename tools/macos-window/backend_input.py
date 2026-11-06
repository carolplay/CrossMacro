"""Typed native inputs alongside the unchanged CUA adapter during migration."""
import json

def click(client, point):
    if getattr(client, 'native_protocol', None) is True:
        return client.click(point)
    return client.js('await target.click(%s); await target.getAXState();' % json.dumps(point))

def key(client, key, count=1, duration_ms=600):
    if getattr(client, 'native_protocol', None) is True:
        return client.key(key, count=count, duration_ms=duration_ms)
    return client.js('for(let i=0;i<%d;i++){ await target.pressKey(%s, {durationMs:%d}); await target.getAXState({emit:false}); }' %
                     (count,json.dumps(key),duration_ms))
