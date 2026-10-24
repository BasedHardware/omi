"""Writes the environment of a running process (macOS, KERN_PROCARGS2) as KEY=VALUE lines, NUL-free."""
import ctypes, sys, struct
pid=int(sys.argv[1]); out=sys.argv[2]
libc=ctypes.CDLL(None)
mib=(ctypes.c_int*3)(1,49,pid)  # CTL_KERN, KERN_PROCARGS2
size=ctypes.c_size_t(1<<20); buf=ctypes.create_string_buffer(size.value)
assert libc.sysctl(mib,3,buf,ctypes.byref(size),None,0)==0
raw=buf.raw[:size.value]; argc=struct.unpack("i",raw[:4])[0]
parts=raw[4:].split(b"\0"); parts=[p for p in parts if p]
env=parts[1+argc:]
with open(out,"w") as f:
    for e in env:
        s=e.decode(errors="replace")
        if "=" in s and s.split("=",1)[0].replace("_","").isalnum(): f.write(s+"\n")
