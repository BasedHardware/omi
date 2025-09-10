# Omi AI's EMG Electromyography (Silent Talk) Project

## Electrode Placement Diagram
<img width="400" alt="Electrode placement" src="./assets/diagram.png">

---

## Channel Assignments (OpenBCI Ganglion)

Each channel has two pins:
- **Upper pin = positive (+)**
- **Lower pin = negative (–)**

REF and BIAS are separate pins.

| Channel | Upper (+) Electrode Placement                  | Lower (–) Electrode Placement                | Notes |
|---------|------------------------------------------------|----------------------------------------------|-------|
| **CH1** | Cheekbone side of **masseter**                 | Jaw angle side of **masseter**               | Side of jaw muscle |
| **CH2** | Masseter bulge (slightly higher on muscle)     | Masseter lower (closer to jaw angle)         | Optional second jaw channel |
| **CH3** | Just below lower lip (**chin center**)         | 2–3 cm further down along midline of chin    | Mentalis muscle |
| **CH4** | Under lip corner / alt. chin spot              | 2–3 cm further down                          | Chin / lip articulation |
| **REF** | Forehead (center, bony area)                   | —                                            | Reference electrode |
| **BIAS**| Mastoid (behind ear) or shoulder               | —                                            | Ground electrode |

---

Check https://docs.openbci.com/GettingStarted/Biosensing-Setups/EEGSetup/?_gl=1*1k7t9el*_gcl_aw*R0NMLjE3NTc0Nzc0MjMuQ2owS0NRandvUF9GQmhERkFSSXNBTlBHMjRNSHVQQTdPdm13d2JvdHZDNTlaZmNoNnZZS2ZYOHF3V0NNdnhvNXhLWWd2SER2Q0ZFMllNd2FBdFN3RUFMd193Y0I.*_gcl_au*NzYwNjY2Nzk1LjE3NTc0NzE1MDI.*_ga*MTUyOTc0OTM2MS4xNzU3NDcxNTAy*_ga_HVMLC0ZWWS*czE3NTc0NzY0MzckbzIkZzEkdDE3NTc0Nzc0MjMkajYwJGwwJGgw#what-you-will-need to learn how to connnect gold cup electrodes

## Placement Guide

### Masseter (Jaw) – CH1 & CH2
- Location: Side of the face, between cheekbone and jaw angle.  
- How to find: Place fingers on jaw and **clench teeth** → feel the bulge.  
- Placement:  
  - **CH1+:** just above bulge (closer to cheekbone)  
  - **CH1–:** near jaw angle  
  - **CH2+:** higher on bulge  
  - **CH2–:** 2–3 cm lower  

### Chin / Lips (Mentalis) – CH3 & CH4
- Location: Center of chin under lower lip (mentalis).  
- Placement:  
  - **CH3+:** just below lower lip (chin center)  
  - **CH3–:** 2–3 cm further down along chin midline  
  - **CH4+:** under lip corner (optional alt.)  
  - **CH4–:** 2–3 cm lower  

### Reference (REF)
- Pin: `REF`  
- Placement: Center forehead (bony area).  

### Bias / Ground (BIAS)
- Pin: `BIAS`  
- Placement: Mastoid (behind ear) or shoulder.  
