@ boot_anim.s - the boot screen as an animation (tools/features/boot_anim.py chains ba_paint after the boot view's paint):
@ the boot picture (the splash feature's) shows for BA_INTRO_US from the first paint, then the picture cycles through BA_FRAMES,
@ one each BA_STEP_US, until the boot view goes. A frame is a whole 320x240 image swapped into the boot view's picture widget;
@ it is redrawn only when the frame changes. The boot view's own paint takes no widget lock, and neither does this.
.syntax unified
.thumb
.include "boot_anim.inc"

.equ DEMCR, 0xe000edfc             @ bit 24 TRCENA: the DWT on
.equ DWT_CTRL, 0xe0001000           @ bit 0 CYCCNTENA: its cycle counter counting
.equ DWT_CYCCNT, 0xe0001004
.equ CPU_MHZ, 204                   @ the core clock the counter counts
.equ IMG_SET, 0x28e24c19            @ (widget, image index)
.equ IMG_DRAW, 0x28e24a01           @ (fb, 0, widget): draws it when its node is dirty, as the boot paint calls it
.equ PICTURE, 0x2811ed30            @ the boot view's picture widget; its node at +0x20, dirty byte at node +0x24

.thumb_func
ba_paint:                           @ r0 the framebuffer, after the boot view's paint
    push {r4-r6, lr}
    mov r4, r0
    bl ba_clock
    adr.w r5, ba_state
    ldr r1, [r5]
    cbnz r1, ba_started
    str r0, [r5, #4]                @ the first paint's time
    movs r1, #1
    str r1, [r5]
    b ba_timed
ba_started:
    ldr r1, [r5, #8]
    cbnz r1, ba_timed               @ the frames have started: no going back to the intro
    ldr r1, [r5, #12]
    subs r1, r0, r1
    ldr r2, =BA_GAP_US
    cmp r1, r2
    it hi
    strhi r0, [r5, #4]              @ a long pause before this paint (the app still starting up): the intro counts from here
ba_timed:
    str r0, [r5, #12]               @ this paint's time
    ldr r1, [r5, #4]
    subs r0, r0, r1                 @ since the first paint; a wrap of the clock is harmless here
    ldr r1, =BA_INTRO_US
    cmp r0, r1
    blo ba_out                      @ the boot picture still shows
    subs r0, r0, r1
    ldr r1, =BA_STEP_US
    udiv r0, r0, r1
    movs r1, #BA_COUNT
    udiv r2, r0, r1
    mls r0, r2, r1, r0              @ the frame
    adr.w r1, ba_frames
    ldrh.w r6, [r1, r0, lsl #1]
    ldr r0, [r5, #8]
    cmp r0, r6
    beq ba_out
    str r6, [r5, #8]
    ldr r0, =PICTURE
    mov r1, r6
    ldr r3, =IMG_SET
    blx r3
    ldr r2, =PICTURE
    ldr r0, [r2, #0x20]
    movs r1, #1
    strb r1, [r0, #0x24]            @ dirty, whatever setImage left
    mov r0, r4
    movs r1, #0
    ldr r3, =IMG_DRAW
    blx r3
ba_out:
    movs r0, #0
    pop {r4-r6, pc}

.thumb_func
ba_clock:                           @ -> r0 µs since the first call, from the core's cycle counter
    @ Not the app's µs clock (0x28da6458, hardware timer 1): the boot view paints before the app sets that timer up, and its
    @ register then faults when started by the stock bootloader (an installed build hung at the bootloader's picture
    @ [verified on unit, 2026-11-15]; a RAM run's loader leaves it usable). The cycle counter is in the core: reading it never
    @ faults. The app turns it on itself later (0x28dadd34); turning it on here as well changes nothing for it.
    ldr r1, =DEMCR
    ldr r2, [r1]
    orr r2, r2, #0x1000000
    str r2, [r1]
    ldr r1, =DWT_CTRL
    ldr r2, [r1]
    orr r2, r2, #1
    str r2, [r1]
    ldr r1, =DWT_CYCCNT
    ldr r0, [r1]
    adr.w r3, ba_clock_state
    ldr r1, [r3]
    cbnz r1, clock_on
    movs r1, #1
    str r1, [r3]
    str r0, [r3, #4]
clock_on:
    ldr r1, [r3, #4]
    str r0, [r3, #4]
    subs r0, r0, r1                 @ cycles since the last call (one wrap of the counter, 21 s, is harmless)
    ldr r1, [r3, #8]
    add r0, r1                      @ with the cycles left over from the last µs
    movs r2, #CPU_MHZ
    udiv r1, r0, r2
    mls r0, r1, r2, r0
    str r0, [r3, #8]
    ldr r0, [r3, #12]
    add r0, r1
    str r0, [r3, #12]
    bx lr

.ltorg
.balign 4
ba_clock_state:                     @ started, the counter at the last call, cycles left over, µs so far
    .word 0, 0, 0, 0
ba_state:                           @ started, the intro's start (µs), the frame shown (image index, 0 for none yet), the last paint's time
    .word 0, 0, 0, 0
ba_frames:
    BA_FRAME_LIST
.balign 4
