@ boot_anim.s - the boot screen as an animation (tools/features/boot_anim.py chains ba_paint after the boot view's paint):
@ the boot picture (the splash feature's) shows for BA_INTRO_US from the first paint, then the picture cycles through BA_FRAMES,
@ one each BA_STEP_US, until the boot view goes. A frame is a whole 320x240 image swapped into the boot view's picture widget;
@ it is redrawn only when the frame changes. The boot view's own paint takes no widget lock, and neither does this.
.syntax unified
.thumb
.include "boot_anim.inc"

.equ CLOCK, 0x28da6459              @ the µs clock
.equ IMG_SET, 0x28e24c19            @ (widget, image index)
.equ IMG_DRAW, 0x28e24a01           @ (fb, 0, widget): draws it when its node is dirty, as the boot paint calls it
.equ PICTURE, 0x2811ed30            @ the boot view's picture widget; its node at +0x20, dirty byte at node +0x24

.thumb_func
ba_paint:                           @ r0 the framebuffer, after the boot view's paint
    push {r4-r6, lr}
    mov r4, r0
    ldr r3, =CLOCK
    blx r3
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

.ltorg
.balign 4
ba_state:                           @ started, the intro's start (µs), the frame shown (image index, 0 for none yet), the last paint's time
    .word 0, 0, 0, 0
ba_frames:
    BA_FRAME_LIST
.balign 4
