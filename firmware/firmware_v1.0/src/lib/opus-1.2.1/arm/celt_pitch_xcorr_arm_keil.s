; Copyright (c) 2007-2008 CSIRO
; Copyright (c) 2007-2009 Xiph.Org Foundation
; Copyright (c) 2013      Parrot
; Written by Aurélien Zanelli
;
; Redistribution and use in source and binary forms, with or without
; modification, are permitted provided that the following conditions
; are met:
;
; - Redistributions of source code must retain the above copyright
; notice, this list of conditions and the following disclaimer.
;
; - Redistributions in binary form must reproduce the above copyright
; notice, this list of conditions and the following disclaimer in the
; documentation and/or other materials provided with the distribution.
;
; THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
; ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
; LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
; A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER
; OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
; EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
; PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
; PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
; LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
; NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
; SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

    AREA  |.text|, CODE, READONLY

    EXPORT celt_pitch_xcorr_edsp

xcorr_kernel_edsp PROC
xcorr_kernel_edsp_start

    ; input:
    ;   r3      = int         len
    ;   r4      = opus_val16 *_x (must be 32-bit aligned)
    ;   r5      = opus_val16 *_y (must be 32-bit aligned)
    ;   r6...r9 = opus_val32  sum[4]
    ; output:
    ;   r6...r9 = opus_val32  sum[4]
    ; preserved: r0-r5
    ; internal usage
    ;   r2      = int         j
    ;   r12,r14 = opus_val16  x[4]
    ;   r10,r11 = opus_val16  y[4]

    STMFD        sp!, {r2,r4,r5,lr}
    LDR          r10, [r5], #4      ; Load y[0...1]
    SUBS         r2, r3, #4         ; j = len-4
    LDR          r11, [r5], #4      ; Load y[2...3]
    BLE xcorr_kernel_edsp_process4_done
    LDR          r12, [r4], #4      ; Load x[0...1]
    ; Stall
xcorr_kernel_edsp_process4
    ; The multiplies must issue from pipeline 0, and can't dual-issue with each
    ; other. Every other instruction here dual-issues with a multiply, and is
    ; thus "free". There should be no stalls in the body of the loop.
    SMLABB       r6, r12, r10, r6   ; sum[0] = MAC16_16(sum[0],x_0,y_0)
    LDR          r14, [r4], #4      ; Load x[2...3]
    SMLABT       r7, r12, r10, r7   ; sum[1] = MAC16_16(sum[1],x_0,y_1)
    SUBS         r2, r2, #4         ; j-=4
    SMLABB       r8, r12, r11, r8   ; sum[2] = MAC16_16(sum[2],x_0,y_2)
    SMLABT       r9, r12, r11, r9   ; sum[3] = MAC16_16(sum[3],x_0,y_3)
    SMLATT       r6, r12, r10, r6   ; sum[0] = MAC16_16(sum[0],x_1,y_1)
    LDR          r10, [r5], #4      ; Load y[4...5]
    SMLATB       r7, r12, r11, r7   ; sum[1] = MAC16_16(sum[1],x_1,y_2)
    SMLATT       r8, r12, r11, r8   ; sum[2] = MAC16_16(sum[2],x_1,y_3)
    SMLATB       r9, r12, r10, r9   ; sum[3] = MAC16_16(sum[3],x_1,y_4)
    LDRGT        r12, [r4], #4      ; Load x[0...1]
    SMLABB       r6, r14, r11, r6   ; sum[0] = MAC16_16(sum[0],x_2,y_2)
    SMLABT       r7, r14, r11, r7   ; sum[1] = MAC16_16(sum[1],x_2,y_3)
    SMLABB       r8, r14, r10, r8   ; sum[2] = MAC16_16(sum[2],x_2,y_4)
    SMLABT       r9, r14, r10, r9   ; sum[3] = MAC16_16(sum[3],x_2,y_5)
    SMLATT       r6, r14, r11, r6   ; sum[0] = MAC16_16(sum[0],x_3,y_3)
    LDR          r11, [r5], #4      ; Load y[6...7]
    SMLATB       r7, r14, r10, r7   ; sum[1] = MAC16_16(sum[1],x_3,y_4)
    SMLATT       r8, r14, r10, r8   ; sum[2] = MAC16_16(sum[2],x_3,y_5)
    SMLATB       r9, r14, r11, r9   ; sum[3] = MAC16_16(sum[3],x_3,y_6)
    BGT xcorr_kernel_edsp_process4
xcorr_kernel_edsp_process4_done
    ADDS         r2, r2, #4
    BLE xcorr_kernel_edsp_done
    LDRH         r12, [r4], #2      ; r12 = *x++
    SUBS         r2, r2, #1         ; j--
    ; Stall
    SMLABB       r6, r12, r10, r6   ; sum[0] = MAC16_16(sum[0],x,y_0)
    LDRHGT       r14, [r4], #2      ; r14 = *x++
    SMLABT       r7, r12, r10, r7   ; sum[1] = MAC16_16(sum[1],x,y_1)
    SMLABB       r8, r12, r11, r8   ; sum[2] = MAC16_16(sum[2],x,y_2)
    SMLABT       r9, r12, r11, r9   ; sum[3] = MAC16_16(sum[3],x,y_3)
    BLE xcorr_kernel_edsp_done
    SMLABT       r6, r14, r10, r6   ; sum[0] = MAC16_16(sum[0],x,y_1)
    SUBS         r2, r2, #1         ; j--
    SMLABB       r7, r14, r11, r7   ; sum[1] = MAC16_16(sum[1],x,y_2)
    LDRH         r10, [r5], #2      ; r10 = y_4 = *y++
    SMLABT       r8, r14, r11, r8   ; sum[2] = MAC16_16(sum[2],x,y_3)
    LDRHGT       r12, [r4], #2      ; r12 = *x++
    SMLABB       r9, r14, r10, r9   ; sum[3] = MAC16_16(sum[3],x,y_4)
    BLE xcorr_kernel_edsp_done
    SMLABB       r6, r12, r11, r6   ; sum[0] = MAC16_16(sum[0],tmp,y_2)
    CMP          r2, #1             ; j--
    SMLABT       r7, r12, r11, r7   ; sum[1] = MAC16_16(sum[1],tmp,y_3)
    LDRH         r2, [r5], #2       ; r2 = y_5 = *y++
    SMLABB       r8, r12, r10, r8   ; sum[2] = MAC16_16(sum[2],tmp,y_4)
    LDRHGT       r14, [r4]          ; r14 = *x
    SMLABB       r9, r12, r2, r9    ; sum[3] = MAC16_16(sum[3],tmp,y_5)
    BLE xcorr_kernel_edsp_done
    SMLABT       r6, r14, r11, r6   ; sum[0] = MAC16_16(sum[0],tmp,y_3)
    LDRH         r11, [r5]          ; r11 = y_6 = *y
    SMLABB       r7, r14, r10, r7   ; sum[1] = MAC16_16(sum[1],tmp,y_4)
    SMLABB       r8, r14, r2, r8    ; sum[2] = MAC16_16(sum[2],tmp,y_5)
    SMLABB       r9, r14, r11, r9   ; sum[3] = MAC16_16(sum[3],tmp,y_6)
xcorr_kernel_edsp_done
    LDMFD        sp!, {r2,r4,r5,pc}
    ENDP

celt_pitch_xcorr_edsp PROC

    ; input:
    ;   r0  = opus_val16 *_x (must be 32-bit aligned)
    ;   r1  = opus_val16 *_y (only needs to be 16-bit aligned)
    ;   r2  = opus_val32 *xcorr
    ;   r3  = int         len
    ; output:
    ;   r0  = maxcorr
    ; internal usage
    ;   r4  = opus_val16 *x
    ;   r5  = opus_val16 *y
    ;   r6  = opus_val32  sum0
    ;   r7  = opus_val32  sum1
    ;   r8  = opus_val32  sum2
    ;   r9  = opus_val32  sum3
    ;   r1  = int         max_pitch
    ;   r12 = int         j
    ; ignored:
    ;         int         arch

    STMFD        sp!, {r4-r11, lr}
    MOV          r5, r1
    LDR          r1, [sp, #36]
    MOV          r4, r0
    TST          r5, #3
    ; maxcorr = 1
    MOV          r0, #1
    BEQ          celt_pitch_xcorr_edsp_process1u_done
; Compute one sum at the start to make y 32-bit aligned.
    SUBS         r12, r3, #4
    ; r14 = sum = 0
    MOV          r14, #0
    LDRH         r8, [r5], #2
    BLE celt_pitch_xcorr_edsp_process1u_loop4_done
    LDR          r6, [r4], #4
    MOV          r8, r8, LSL #16
celt_pitch_xcorr_edsp_process1u_loop4
    LDR          r9, [r5], #4
    SMLABT       r14, r6, r8, r14     ; sum = MAC16_16(sum, x_0, y_0)
    LDR          r7, [r4], #4
    SMLATB       r14, r6, r9, r14     ; sum = MAC16_16(sum, x_1, y_1)
    LDR          r8, [r5], #4
    SMLABT       r14, r7, r9, r14     ; sum = MAC16_16(sum, x_2, y_2)
    SUBS         r12, r12, #4         ; j-=4
    SMLATB       r14, r7, r8, r14     ; sum = MAC16_16(sum, x_3, y_3)
    LDRGT        r6, [r4], #4
    BGT celt_pitch_xcorr_edsp_process1u_loop4
    MOV          r8, r8, LSR #16
celt_pitch_xcorr_edsp_process1u_loop4_done
    ADDS         r12, r12, #4
celt_pitch_xcorr_edsp_process1u_loop1
    LDRHGE       r6, [r4], #2
    ; Stall
    SMLABBGE     r14, r6, r8, r14    ; sum = MAC16_16(sum, *x, *y)
    SUBSGE       r12, r12, #1
    LDRHGT       r8, [r5], #2
    BGT celt_pitch_xcorr_edsp_process1u_loop1
    ; Restore _x
    SUB          r4, r4, r3, LSL #1
    ; Restore and advance _y
    SUB          r5, r5, r3, LSL #1
    ; maxcorr = max(maxcorr, sum)
    CMP          r0, r14
    ADD          r5, r5, #2
    MOVLT        r0, r14
    SUBS         r1, r1, #1
    ; xcorr[i] = sum
    STR          r14, [r2], #4
    BGT celt_pitch_xcorr_edsp_process1u_done
    B   celt_pitch_xcorr_edsp_done
celt_pitch_xcorr_edsp_process1u_done
    ; if (max_pitch < 4) goto celt_pitch_xcorr_edsp_process2
    SUBS         r1, r1, #4
    BLT celt_pitch_xcorr_edsp_process2
celt_pitch_xcorr_edsp_process4
    ; xcorr_kernel_edsp parameters:
    ; r3 = len, r4 = _x, r5 = _y, r6...r9 = sum[4] = {0, 0, 0, 0}
    MOV          r6, #0
    MOV          r7, #0
    MOV          r8, #0
    MOV          r9, #0
    BL xcorr_kernel_edsp_start  ; xcorr_kernel_edsp(_x, _y+i, xcorr+i, len)
    ; maxcorr = max(maxcorr, sum0, sum1, sum2, sum3)
    CMP          r0, r6
    ; _y+=4
    ADD          r5, r5, #8
    MOVLT        r0, r6
    CMP          r0, r7
    MOVLT        r0, r7
    CMP          r0, r8
    MOVLT        r0, r8
    CMP          r0, r9
    MOVLT        r0, r9
    STMIA        r2!, {r6-r9}
    SUBS         r1, r1, #4
    BGE celt_pitch_xcorr_edsp_process4
celt_pitch_xcorr_edsp_process2
    ADDS         r1, r1, #2
    BLT celt_pitch_xcorr_edsp_process1a
    SUBS         r12, r3, #4
    ; {r10, r11} = {sum0, sum1} = {0, 0}
    MOV          r10, #0
    MOV          r11, #0
    LDR          r8, [r5], #4
    BLE celt_pitch_xcorr_edsp_process2_loop_done
    LDR          r6, [r4], #4
    LDR          r9, [r5], #4
celt_pitch_xcorr_edsp_process2_loop4
    SMLABB       r10, r6, r8, r10     ; sum0 = MAC16_16(sum0, x_0, y_0)
    LDR          r7, [r4], #4
    SMLABT       r11, r6, r8, r11     ; sum1 = MAC16_16(sum1, x_0, y_1)
    SUBS         r12, r12, #4         ; j-=4
    SMLATT       r10, r6, r8, r10     ; sum0 = MAC16_16(sum0, x_1, y_1)
    LDR          r8, [r5], #4
    SMLATB       r11, r6, r9, r11     ; sum1 = MAC16_16(sum1, x_1, y_2)
    LDRGT        r6, [r4], #4
    SMLABB       r10, r7, r9, r10     ; sum0 = MAC16_16(sum0, x_2, y_2)
    SMLABT       r11, r7, r9, r11     ; sum1 = MAC16_16(sum1, x_2, y_3)
    SMLATT       r10, r7, r9, r10     ; sum0 = MAC16_16(sum0, x_3, y_3)
    LDRGT        r9, [r5], #4
    SMLATB       r11, r7, r8, r11     ; sum1 = MAC16_16(sum1, x_3, y_4)
    BGT celt_pitch_xcorr_edsp_process2_loop4
celt_pitch_xcorr_edsp_process2_loop_done
    ADDS         r12, r12, #2
    BLE  celt_pitch_xcorr_edsp_process2_1
    LDR          r6, [r4], #4
    ; Stall
    SMLABB       r10, r6, r8, r10     ; sum0 = MAC16_16(sum0, x_0, y_0)
    LDR          r9, [r5], #4
    SMLABT       r11, r6, r8, r11     ; sum1 = MAC16_16(sum1, x_0, y_1)
    SUB          r12, r12, #2
    SMLATT       r10, r6, r8, r10     ; sum0 = MAC16_16(sum0, x_1, y_1)
    MOV          r8, r9
    SMLATB       r11, r6, r9, r11     ; sum1 = MAC16_16(sum1, x_1, y_2)
celt_pitch_xcorr_edsp_process2_1
    LDRH         r6, [r4], #2
    ADDS         r12, r12, #1
    ; Stall
    SMLABB       r10, r6, r8, r10     ; sum0 = MAC16_16(sum0, x_0, y_0)
    LDRHGT       r7, [r4], #2
    SMLABT       r11, r6, r8, r11     ; sum1 = MAC16_16(sum1, x_0, y_1)
    BLE celt_pitch_xcorr_edsp_process2_done
    LDRH         r9, [r5], #2
    SMLABT       r10, r7, r8, r10     ; sum0 = MAC16_16(sum0, x_0, y_1)
    SMLABB       r11, r7, r9, r11     ; sum1 = MAC16_16(sum1, x_0, y_2)
celt_pitch_xcorr_edsp_process2_done
    ; Restore _x
    SUB          r4, r4, r3, LSL #1
    ; Restore and advance _y
    SUB          r5, r5, r3, LSL #1
    ; maxcorr = max(maxcorr, sum0)
    CMP          r0, r10
    ADD          r5, r5, #2
    MOVLT        r0, r10
    SUB          r1, r1, #2
    ; maxcorr = max(maxcorr, sum1)
    CMP          r0, r11
    ; xcorr[i] = sum
    STR          r10, [r2], #4
    MOVLT        r0, r11
    STR          r11, [r2], #4
celt_pitch_xcorr_edsp_process1a
    ADDS         r1, r1, #1
    BLT celt_pitch_xcorr_edsp_done
    SUBS         r12, r3, #4
    ; r14 = sum = 0
    MOV          r14, #0
    BLT celt_pitch_xcorr_edsp_process1a_loop_done
    LDR          r6, [r4], #4
    LDR          r8, [r5], #4
    LDR          r7, [r4], #4
    LDR          r9, [r5], #4
celt_pitch_xcorr_edsp_process1a_loop4
    SMLABB       r14, r6, r8, r14     ; sum = MAC16_16(sum, x_0, y_0)
    SUBS         r12, r12, #4         ; j-=4
    SMLATT       r14, r6, r8, r14     ; sum = MAC16_16(sum, x_1, y_1)
    LDRGE        r6, [r4], #4
    SMLABB       r14, r7, r9, r14     ; sum = MAC16_16(sum, x_2, y_2)
    LDRGE        r8, [r5], #4
    SMLATT       r14, r7, r9, r14     ; sum = MAC16_16(sum, x_3, y_3)
    LDRGE        r7, [r4], #4
    LDRGE        r9, [r5], #4
    BGE celt_pitch_xcorr_edsp_process1a_loop4
celt_pitch_xcorr_edsp_process1a_loop_done
    ADDS         r12, r12, #2
    LDRGE        r6, [r4], #4
    LDRGE        r8, [r5], #4
    ; Stall
    SMLABBGE     r14, r6, r8, r14     ; sum = MAC16_16(sum, x_0, y_0)
    SUBGE        r12, r12, #2
    SMLATTGE     r14, r6, r8, r14     ; sum = MAC16_16(sum, x_1, y_1)
    ADDS         r12, r12, #1
    LDRHGE       r6, [r4], #2
    LDRHGE       r8, [r5], #2
    ; Stall
    SMLABBGE     r14, r6, r8, r14     ; sum = MAC16_16(sum, *x, *y)
    ; maxcorr = max(maxcorr, sum)
    CMP          r0, r14
    ; xcorr[i] = sum
    STR          r14, [r2], #4
    MOVLT        r0, r14
celt_pitch_xcorr_edsp_done
    LDMFD        sp!, {r4-r11, pc}
    ENDP

    END
