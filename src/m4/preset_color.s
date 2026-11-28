@ preset_color.s - in Preset footswitch mode, each preset's footswitch in its colour: This Preset's, kept in the preset file as key
@ 0x65, lit while the preset is selected and dimmed while it is not; a preset without one lit in Preset LED Color's and off while not
@ selected, as stock. The ring and the switch icon on the Home screen both. tools/features/preset_color.py places the hooks.
.syntax unified
.thumb
.include "hxtra.inc"
.equ LED_COLOUR, 0x28db81fd         @ (led, 0xBBGGRR): the colour an LED shows while it is on; sends it at once to a lit one
.equ LED_MODE, 0x28db8261           @ (led, mode): 0 off, 1 on, 2 blink
.equ SET_IMAGE, 0x28e24c19          @ (image widget, image index)
.equ LED_MODES, 0x281f35f8          @ each ring's mode byte
.equ FS_FUNCTIONS, 0x28128a74       @ each footswitch's function, two bytes apart
.equ FS_STATE, 0x28d9607d           @ () -> the footswitches' state, as the LED refresh passes it
.equ FS_PRESET, 0x28dd5455          @ (state, footswitch, &preset) -> < 0 when it has none
.equ CUR_REF, 0x28df024d            @ (ref) -> ref {setlist, slot} of the current preset
.equ DIR, 0x28df0635                @ (ref, out): the directory entry {file id, name}, 0x24 bytes
.equ H_INIT, 0x28def7b5             @ (id, name, handle): a preset file handle, 0x188 bytes
.equ H_OPEN, 0x28df006d             @ (handle) -> < 0 failed
.equ H_CLOSE, 0x28defde1            @ (handle)
.equ FS_SEEK, 0x28daa2d9            @ (file, offset, 0): from the start
.equ FS_READ, 0x28daa269            @ (file, buffer, n) -> bytes read
.equ FS_SIZE, 0x28daa3ed            @ (file) -> its length, the end the load's section 10 runs to
.equ H_FILE, 0x18                   @ in a handle: the store file
.equ PRESET, 13                     @ the function Preset mode gives FS1..FS3
.equ ICON, 0x3f4                    @ in the Home view: footswitch k's switch icon, image widgets 0x24 bytes apart
.equ RED_ICON, 0x78                 @ Icon_SwitchRed, the current preset's
.equ DARK_ICON, 0x112               @ Icon_SwitchDark, the others'
.equ RINGS, 3
.equ PRESET_KEY, 0x65
.equ PRESET_MAGIC, 0x43505848       @ "HXPC", little-endian

.thumb_func
.global preset_led
preset_led:                         @ the LED refresh's Preset case, (led, red): the current preset's ring in its colour, lit
    push {r0, lr}
    bl preset_lit
    adr.w r1, preset_leds
    ldr.w r1, [r1, r0, lsl #2]
    pop {r0, lr}
    ldr r3, =LED_COLOUR
    bx r3

.thumb_func
.global preset_off
preset_off:                         @ the LED refresh's call that turns a ring off (led, 0): a Preset ring of a coloured preset dims
    ldr r2, =FS_FUNCTIONS
    ldrb.w r2, [r2, r0, lsl #1]
    cmp r2, #PRESET
    beq 1f
    ldr r3, =LED_MODE
    bx r3
1:  push {r4, r5, lr}
    sub sp, #12
    mov r4, r0
    ldr r3, =FS_STATE
    blx r3
    mov r1, r4
    add r2, sp, #4
    movs r3, #0
    str r3, [r2]
    ldr r3, =FS_PRESET
    blx r3
    cmp r0, #0
    blt preset_off_stock
    ldrb.w r0, [sp, #4]
    bl preset_colour_of
    cbz r0, preset_off_stock
    adr.w r1, preset_dims
    subs r0, #1
    ldr.w r5, [r1, r0, lsl #2]
    mov r0, r4
    movs r1, #1
    ldr r3, =LED_MODE
    blx r3
    mov r0, r4
    mov r1, r5
    ldr r3, =LED_COLOUR
    blx r3
    b preset_off_done
preset_off_stock:
    mov r0, r4
    movs r1, #0
    ldr r3, =LED_MODE
    blx r3
preset_off_done:
    add sp, #12
    pop {r4, r5, pc}

.thumb_func
.global preset_icon
preset_icon:                        @ the Preset-mode Home builder, setImage (widget, Icon_SwitchRed or Icon_SwitchDark), r4 the preset
    cmp r1, #RED_ICON
    beq preset_icon_lit
    cmp r1, #DARK_ICON
    bne preset_icon_set
    push {r0, r1, r4, lr}
    mov r0, r4
    bl preset_colour_of
    mov r2, r0
    pop {r0, r1, r4, lr}
    cbz r2, preset_icon_set
    adr.w r1, preset_dim_icons
    subs r2, #1
    ldr.w r1, [r1, r2, lsl #2]
    b preset_icon_set
preset_icon_lit:
    push {r0, lr}
    bl preset_lit
    adr.w r1, preset_icons
    ldr.w r1, [r1, r0, lsl #2]
    pop {r0, lr}
preset_icon_set:
    ldr r3, =SET_IMAGE
    bx r3

.thumb_func
.global preset_paint
preset_paint:                       @ before the Home paint (framebuffer, Home view): a changed setting recolours the lit Preset ring
    push {r4-r8, lr}
    mov r4, r1
    bl preset_setting
    mov r5, r0
    bl preset_this
    orr.w r0, r5, r0, lsl #4
    adr.w r1, preset_shown
    ldrb r2, [r1]
    cmp r2, r0
    beq preset_paint_done
    strb r0, [r1]                   @ leaving Global Settings rebuilds no label and relights no ring
    bl preset_lit
    adr.w r1, preset_leds
    ldr.w r6, [r1, r0, lsl #2]
    adr.w r1, preset_icons
    ldr.w r7, [r1, r0, lsl #2]
    movs r5, #0
preset_paint_each:
    ldr r0, =FS_FUNCTIONS
    ldrb.w r0, [r0, r5, lsl #1]
    cmp r0, #PRESET
    bne preset_paint_next
    ldr r0, =LED_MODES
    ldrb r0, [r0, r5]
    cmp r0, #1
    bne preset_paint_next
    mov r0, r5                      @ a lit ring is the current preset's or a coloured one dimmed: only the current one changes
    bl preset_is_current
    cbz r0, preset_paint_next
    mov r0, r5
    mov r1, r6
    ldr r3, =LED_COLOUR
    blx r3
    movs r0, #0x24
    mul r0, r5, r0
    add r0, r4
    add.w r0, r0, #ICON
    mov r1, r7
    ldr r3, =SET_IMAGE
    blx r3
preset_paint_next:
    adds r5, #1
    cmp r5, #RINGS
    bne preset_paint_each
preset_paint_done:
    pop {r4-r8, pc}

preset_is_current:                  @ (footswitch) -> r0 1 when its preset is the current one
    push {r4, lr}
    sub sp, #16                     @ ref 8, then the footswitch's preset
    mov r4, r0
    ldr r3, =FS_STATE
    blx r3
    mov r1, r4
    add r2, sp, #12
    movs r3, #0
    str r3, [r2]
    ldr r3, =FS_PRESET
    blx r3
    cmp r0, #0
    blt preset_is_not
    mov r0, sp
    ldr r3, =CUR_REF
    blx r3
    ldrb.w r0, [sp, #12]
    ldr r1, [sp, #4]
    cmp r0, r1
    bne preset_is_not
    movs r0, #1
    b preset_is_done
preset_is_not:
    movs r0, #0
preset_is_done:
    add sp, #16
    pop {r4, pc}

preset_colour_of:                   @ (preset) -> r0 its colour in its file, 1 Red .. 10 White, or 0: the last 8 bytes of the file
    push {r4-r6, lr}
    sub sp, #0x1c8                  @ ref 8, directory entry 0x24, the tail 8, the handle 0x188 at 0x40
    mov r4, r0
    mov r0, sp
    ldr r3, =CUR_REF
    blx r3
    str r4, [sp, #4]
    mov r0, sp
    add r1, sp, #8
    ldr r3, =DIR
    blx r3
    add r6, sp, #0x40
    ldr r0, [sp, #8]
    add r1, sp, #12
    mov r2, r6
    ldr r3, =H_INIT
    blx r3
    mov r0, r6
    ldr r3, =H_OPEN
    blx r3
    movs r5, #0
    cmp r0, #0
    blt preset_colour_done
    add.w r0, r6, #H_FILE
    ldr r3, =FS_SIZE
    blx r3
    subs r1, r0, #8
    add.w r0, r6, #H_FILE
    movs r2, #0
    ldr r3, =FS_SEEK
    blx r3
    add.w r0, r6, #H_FILE
    add r1, sp, #0x2c
    movs r2, #8
    ldr r3, =FS_READ
    blx r3
    mov r4, r0
    mov r0, r6
    ldr r3, =H_CLOSE
    blx r3
    cmp r4, #8
    bne preset_colour_done
    ldr r0, [sp, #0x2c]             @ 65 c4 05 'H', then 'X' 'P' 'C' and the colour
    ldr r1, =PRESET_KEY | 0xc4 << 8 | 5 << 16 | 0x48 << 24
    cmp r0, r1
    bne preset_colour_done
    ldr r0, [sp, #0x30]
    bic r1, r0, #0xff000000
    ldr r2, =PRESET_MAGIC >> 8
    cmp r1, r2
    bne preset_colour_done
    lsrs r0, r0, #24
    cmp r0, #SETTING_PRESET_COLOR_THIS_MAX
    it ls
    movls r5, r0
preset_colour_done:
    mov r0, r5
    add sp, #0x1c8
    pop {r4-r6, pc}

.thumb_func
.global preset_key_write
preset_key_write:                   @ preset_keys.s's writer (stream): This Preset as key 0x65, none for None; -> the keys written
    push {r4, lr}
    mov r4, r0
    bl preset_this
    cbz r0, preset_key_written
    adr.w r1, preset_key_head
    strb r0, [r1, #7]
    movs r2, #8
    ldr r0, [r4]
    ldr r3, [r4, #4]
    blx r3
    movs r0, #1
preset_key_written:
    pop {r4, pc}

.thumb_func
.global preset_key_found
preset_key_found:                   @ preset_keys.s's finder (key, data, length): This Preset from the file, None at START
    cmn r0, #1
    beq preset_key_none
    cmp r0, #PRESET_KEY
    it ne
    bxne lr
    cmp r2, #5
    it ne
    bxne lr
    ldr r0, [r1]
    ldr r3, =PRESET_MAGIC
    cmp r0, r3
    it ne
    bxne lr
    ldrb r1, [r1, #4]
    cmp r1, #SETTING_PRESET_COLOR_THIS_MAX
    it hi
    bxhi lr
    movs r0, #SETTING_PRESET_COLOR_THIS
    b hxtra_setting_set
preset_key_none:
    movs r0, #SETTING_PRESET_COLOR_THIS
    movs r1, #0
    b hxtra_setting_set

preset_lit:                         @ -> r0 the current preset's colour, by palette index: This Preset's, else Preset LED Color's
    push {r3, lr}
    bl preset_this
    cbz r0, 1f
    subs r0, #1
    pop {r3, pc}
1:  pop {r3, lr}
    b preset_setting

preset_this:                        @ -> r0 This Preset: 0 None, 1 Red .. 10 White
    movs r0, #SETTING_PRESET_COLOR_THIS
    movs r1, #SETTING_PRESET_COLOR_THIS_MAX
    movs r2, #SETTING_PRESET_COLOR_THIS_DEFAULT
    b hxtra_setting_get

preset_setting:                     @ -> r0 Preset LED Color
    movs r0, #SETTING_PRESET_COLOR_COLOR
    movs r1, #SETTING_PRESET_COLOR_COLOR_MAX
    movs r2, #SETTING_PRESET_COLOR_COLOR_DEFAULT
    b hxtra_setting_get

HXTRA_SETTING_GET
HXTRA_SETTING_SET
.ltorg
.balign 4
@ The stock palette, by Color: Red, Dk Orange, Lt Orange, Yellow, Green, Turquoise, Blue, Violet, Pink, White
preset_leds:                        @ the LED driver's lit colours (0x28dd8030(_, i, 1))
    .word 0x0300ff, 0x002dff, 0x00afd0, 0x00ff84, 0x00ff06, 0x80ff00, 0xff3200, 0xff0032, 0x2800ff, 0xceff6b
preset_dims:                        @ and its dim ones (0x28dd8030(_, i, 0)), as stock shows a bypassed block
    .word 0x02000c, 0x000410, 0x000608, 0x000c08, 0x000901, 0x060d00, 0x0d0400, 0x0b0003, 0x07000b, 0x0c1007
preset_icons:                       @ Icon_SwitchRed .. Icon_SwitchWhite
    .word 0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115
preset_dim_icons:                   @ Icon_SwitchRedOff .. Icon_SwitchWhiteOff
    .word 0x9c, 0x1e0, 0x214, 0xb7, 0x1fb, 0x8, 0x184, 0xc0, 0x117, 0x76
preset_shown:                       @ the settings the ring was last recoloured for (Preset LED Color | This Preset << 4); none yet
    .word 0xff
preset_key_head:                    @ key 0x65, bin8 of 5: "HXPC" and the colour (1 Red .. 10 White)
    .byte PRESET_KEY, 0xc4, 5, 'H', 'X', 'P', 'C', 0
