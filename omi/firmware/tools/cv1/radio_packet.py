"""Decode bounded nRF RADIO RAM snapshots, not an on-air capture or emulator."""
UUID_LE=bytes.fromhex('14128a7604d16c4f7e53f2e80000b119')
def decode(data,pcnf0):
    if (pcnf0&15)!=8 or ((pcnf0>>8)&1)!=1 or ((pcnf0>>16)&15)!=0:
        raise ValueError('unsupported radio RAM header format')
    start=2+bool(pcnf0&(1<<20))
    if len(data)<start:raise ValueError('truncated header')
    length=data[1]
    if data[0]&15!=0 or length<6 or length>37:raise ValueError('not a valid bounded ADV_IND')
    if len(data)<start+length:raise ValueError('truncated payload')
    ad=data[start+6:start+length];fields=[];i=0
    while i<len(ad):
        n=ad[i]
        if not n:raise ValueError('zero AD length before payload end')
        if i+1+n>len(ad):raise ValueError('truncated AD field')
        fields.append((ad[i+1],ad[i+2:i+n+1]));i+=n+1
    return {'pdu_type':'ADV_IND','random_address':bool(data[0]&64),'payload_bytes':length,
            'name':next((v.decode('utf8') for t,v in fields if t==9),None),
            'omi_service':any(t in (6,7) and len(v)%16==0 and UUID_LE in [v[j:j+16] for j in range(0,len(v),16)] for t,v in fields),
            'flags':next((v[0] for t,v in fields if t==1 and len(v)==1),None)}
