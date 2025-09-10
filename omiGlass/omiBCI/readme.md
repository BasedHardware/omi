# Omi AI's EMG Electromyography (Silent Talk) Project

## Channel Assignments (OpenBCI Ganglion)

Each channel has two pins:
- **Upper pin = positive (+)**
- **Lower pin = negative (–)**

REF and BIAS are separate pins.

| Channel | Upper (+) Electrode Placement                  | Lower (–) Electrode Placement                | Notes |
|---------|------------------------------------------------|----------------------------------------------|-------|
| **CH1** | Cheekbone side of **masseter**                 | Jaw angle side of **masseter**               | Side of jaw muscle |
| **CH3** | Just below lower lip (**chin center**)         | 2–3 cm further down along midline of chin    | Mentalis muscle |
| **REF** | Forehead (center, bony area)                   | —                                            | Reference electrode |
| **D__G (BIAS)**| Mastoid (behind ear) or shoulder               | —                                            | Ground electrode |

---

## Placement Guide

### Masseter (Jaw) – CH1 & CH2
- Location: Side of the face, between cheekbone and jaw angle.  
- How to find: Place fingers on jaw and **clench teeth** → feel the bulge.  
- Placement:  
  - **CH1+:** just above bulge (closer to cheekbone)  
  - **CH1–:** near jaw angle  

### Chin / Lips (Mentalis) – CH3 & CH4
- Location: Center of chin under lower lip (mentalis).  
- Placement:  
  - **CH3+:** just below lower lip (chin center)  
  - **CH3–:** 2–3 cm further down along chin midline  

### Reference (REF)
- Pin: `REF`  
- Placement: Center forehead (bony area).  

### Bias / D__G
- Pin: `BIAS/D__G`  
- Placement: Mastoid (behind ear) or shoulder.  