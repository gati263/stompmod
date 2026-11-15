@ model_pictures.s - a picture of a model on two screens (tools/features/model_pictures.py adds the pictures, patches the Edit view's
@ title fonts and single-row y, and chains these):
@ mp_edit: the selected block's picture in the Edit view, centred between its (smaller) title and its (lower) row of blocks, while
@   the preset has one row; a second row keeps the stock layout's room, so no picture then;
@ mp_browser: the picture of the model under the cursor in the model browser, right of the names; mp_row_text shortens a name
@   that would run into it.
@ A block's model comes from the DSP model's block record (its name index), the selected block from the slot showing a selected
@ picture (MP_SEL: a bit per stock image), and a model's picture from MP_TABLE (an image index per name index, 0 for none;
@ MP_BTABLE, the browser's, names a tall picture's larger copy).
@ Each picture is an image widget of our own, drawn after the stock paint, under the widget lock.
.syntax unified
.thumb
.include "hxtra.inc"
.include "model_pictures.inc"

.equ DSP_PTR, 0x28449e78            @ the DSP model: 0x54-byte block records at +0x14, each its node handle then a name index at +8
.equ SLOT_MODEL, 0x2812c590         @ the UI's slot model: nonzero at +0x23 when the path has a second row, at +0x3f + k when column k shows it
.equ DSP_LOCK, 0x28e07845
.equ DSP_UNLOCK, 0x28e0785d
.equ WIDGET_LOCK, 0x28e24971
.equ WIDGET_UNLOCK, 0x28e24ae9
.equ IMG_INIT, 0x28e24ab1           @ (widget, node)
.equ IMG_SET, 0x28e24c19            @ (widget, image index): its width and height from the image
.equ IMG_POS, 0x28e24c69            @ (widget, x, y)
.equ IMG_ANCHOR, 0x28e24aa9         @ (widget, 3 * row + column)
.equ IMG_VISIBLE, 0x28e24a99        @ (widget, visible)
.equ IMG_ERASE, 0x28e24b69          @ (fb, fb, widget): black over its old and new rectangles, when its node is dirty
.equ IMG_DRAW, 0x28e24a01           @ (fb, fb, widget)
.equ SET_ROW_TEXT, 0x28e24c89       @ the model list's setText(list, row, text)
.equ BROWSER_LEVEL, 0x28df0281      @ (&level): the level byte the list is picked by; takes and releases the DSP model lock
.equ LIST_LENGTH, 0x28e0edcd        @ (category, subcategory) -> the list's length, negative for none
.equ LIST_ITEM, 0x28e01205          @ (category, subcategory, i, &item) -> 0 and the item: {kind, name index, ...}
.equ GLYPHS, 0x28d1aa7c             @ font k's table at GLYPHS + 0x604 * k: its spacing, then 128 {height, width, item}
.equ GLYPHS_STEP, 0x604
.equ BOLD, 2                        @ hx28_boldFont: the model list's selected row
.equ MAX_CHARS, 16                  @ a name holds 16 characters
.equ W_NODE, 0x24                   @ a picture's state: its image widget, its node, then made, shown and its anchor
.equ W_MADE, 0x4c
.equ W_SHOWN, 0x50
.equ W_ANCHOR, 0x54
.equ EDIT_SLOTS, 0x4a4              @ the Edit view's eight block slots, image widgets of 0x24 bytes
.equ MODELS, 2                      @ the browser level that lists models

.thumb_func
mp_edit:                            @ r0 the framebuffer, r1 the Edit view's top half, after its stock paint
    push {r4-r6, lr}
    mov r4, r0
    mov r5, r1
    movs r6, #0
    bl shown
    cbz r0, edit_show
    ldr r0, =SLOT_MODEL
    ldrb r0, [r0, #0x23]
    cbnz r0, edit_show              @ a second row: the stock layout, no room for a picture
    addw r0, r5, #EDIT_SLOTS
    bl selected_model
    ldr r1, =MP_TABLE
    bl image_of
    mov r6, r0
edit_show:
    adr.w r0, edit_pic
    mov r1, r6
    movs r2, #160
    movs r3, #MP_EDIT_Y
    bl show
    movs r0, #0
    pop {r4-r6, pc}

.thumb_func
mp_browser:                         @ r0 the framebuffer, r1 the model browser, after its stock paint
    push {r4-r7, lr}
    sub sp, #12                     @ 0 the level, 4 the item under the cursor, 8 its descriptor
    mov r4, r0
    mov r5, r1
    movs r6, #0
    bl shown
    cmp r0, #0
    beq browser_show
    ldrb r0, [r5, #0x40]
    cmp r0, #MODELS
    bne browser_show
    mov r0, sp
    ldr r3, =BROWSER_LEVEL
    blx r3
    ldrb r0, [sp]
    add r7, r5, r0                  @ the level's bytes: category at +0x56e, subcategory at +0x570
    add.w r1, r5, r0, lsl #2
    ldr.w r1, [r1, #0x574]          @ the item the list shows in bold, as the fill picks it
    str r1, [sp, #4]
    ldrb.w r0, [r7, #0x56e]
    ldrb.w r1, [r7, #0x570]
    ldr r3, =LIST_LENGTH
    blx r3
    cmp r0, #0
    ble browser_show
    ldr r2, [sp, #4]
    cmp r2, r0
    bhs browser_show
    ldrb.w r0, [r7, #0x56e]
    ldrb.w r1, [r7, #0x570]
    add r3, sp, #8
    ldr r12, =LIST_ITEM
    blx r12
    cmp r0, #0
    blt browser_show
    ldr r0, [sp, #8]
    ldr r0, [r0, #4]                @ its name index
    ldr r1, =MP_BTABLE              @ a tall picture's larger copy
    bl image_of
    mov r6, r0
browser_show:
    adr.w r0, browser_pic
    mov r1, r6
    movw r2, #MP_BROWSER_X
    movs r3, #MP_BROWSER_Y
    bl show
    movs r0, #0
    add sp, #12
    pop {r4-r7, pc}

.thumb_func
mp_row_text:                        @ r0 the model list's names, r1 a row, r2 its name: setText, the name shortened with ".." past MP_NAME_MAXW
    push {r4-r10, lr}
    mov r4, r0
    mov r5, r1
    mov r6, r2
    bl shown
    cmp r0, #0
    beq row_set
    mov r0, r6
    movs r1, #BOLD
    bl text_width
    movw r1, #MP_NAME_MAXW
    cmp r0, r1
    ble row_set
    ldr r7, =(GLYPHS + GLYPHS_STEP * BOLD)
    ldr r8, [r7]                    @ the spacing
    ldr r0, [r7, #(8 + 12 * '.')]
    add r0, r8
    sub.w r9, r1, r0, lsl #1        @ what the kept characters may take, with "..": its two dots and their spacing
    adr.w r10, row_short
    movs r3, #0                     @ characters kept
    movs r12, #0                    @ their width, with spacing
row_char:
    cmp r3, #(MAX_CHARS - 2)
    beq row_dots
    ldrb r0, [r6, r3]
    cbz r0, row_dots
    and r0, r0, #0x7f
    add.w r0, r0, r0, lsl #1
    add.w r0, r7, r0, lsl #2
    ldr r0, [r0, #8]
    add r0, r8
    add r0, r12
    cmp r0, r9
    bgt row_dots
    mov r12, r0
    ldrb r0, [r6, r3]
    strb r0, [r10, r3]
    adds r3, #1
    b row_char
row_dots:
    movs r0, #'.'
    strb r0, [r10, r3]
    adds r3, #1
    strb r0, [r10, r3]
    adds r3, #1
    movs r0, #0
    strb r0, [r10, r3]
    mov r6, r10
row_set:
    mov r0, r4
    mov r1, r5
    mov r2, r6
    ldr r3, =SET_ROW_TEXT
    blx r3
    pop {r4-r10, pc}

@ Helpers

.thumb_func
shown:                              @ -> r0 1 when Pictures is On
    push {r3, lr}
    movs r0, #SETTING_MODEL_PICTURES_SHOW
    movs r1, #SETTING_MODEL_PICTURES_SHOW_MAX
    movs r2, #SETTING_MODEL_PICTURES_SHOW_DEFAULT
    bl hxtra_setting_get
    pop {r3, pc}

.thumb_func
selected_model:                     @ r0 a view's first block slot -> r0 the selected block's name index, or -1
    push {r4-r6, lr}
    mov r4, r0
    movs r5, #0
sel_slot:
    ldrb r0, [r4, #0x1d]
    cbz r0, sel_next                @ hidden: an empty slot
    ldr r0, [r4]
    movw r1, #MP_SEL_BITS
    cmp r0, r1
    bhs sel_next
    ldr r1, =MP_SEL
    lsrs r2, r0, #3
    ldrb r2, [r1, r2]
    and r0, r0, #7
    lsrs r2, r0
    lsls r2, r2, #31
    bmi sel_found                   @ a selected picture
sel_next:
    adds r4, #0x24
    adds r5, #1
    cmp r5, #8
    bne sel_slot
    b sel_none
sel_found:
    ldr r1, =SLOT_MODEL
    add r1, r5
    ldrb r1, [r1, #0x3f]
    cbz r1, sel_row
    adds r5, #8                     @ the column shows its second-row block, as the meter takes it
sel_row:
    ldr r6, =DSP_PTR
    ldr r6, [r6]
    cbz r6, sel_none
    movs r0, #0
    ldr r3, =DSP_LOCK
    blx r3
    movs r0, #0x54
    mla r0, r5, r0, r6
    ldr r1, [r0, #0x14]             @ the block's handle
    ldr r4, [r0, #0x1c]             @ its name index
    cmp r1, #0x4b
    it hi
    mvnhi r4, #0                    @ no block
    movs r0, #0
    ldr r3, =DSP_UNLOCK
    blx r3
    mov r0, r4
    pop {r4-r6, pc}
sel_none:
    mvn r0, #0
    pop {r4-r6, pc}

.thumb_func
image_of:                           @ r0 a name index (-1 for none), r1 a picture table -> r0 its picture's image index, 0 for none
    cmp r0, #0
    blt no_image
    movw r2, #MP_COUNT
    cmp r0, r2
    bhs no_image
    ldrh.w r0, [r1, r0, lsl #1]
    bx lr
no_image:
    movs r0, #0
    bx lr

.thumb_func
show:                               @ r0 a picture's state, r1 its image (0: none), r2 x, r3 y, r4 the framebuffer
    push {r4-r8, lr}
    mov r5, r0
    mov r6, r1
    mov r7, r2
    mov r8, r3
    cbnz r6, show_lock
    ldr r0, [r5, #W_SHOWN]
    cmp r0, #0
    beq show_out                    @ hidden and staying hidden: the stock pixels there stay as they are
show_lock:
    ldr r3, =WIDGET_LOCK
    blx r3
    ldr r0, [r5, #W_MADE]
    cbnz r0, show_made
    mov r0, r5
    add r1, r5, #W_NODE
    ldr r3, =IMG_INIT
    blx r3
    mov r0, r5
    ldr r1, [r5, #W_ANCHOR]
    ldr r3, =IMG_ANCHOR
    blx r3
    movs r0, #1
    str r0, [r5, #W_MADE]
show_made:
    movs r1, #0
    cbz r6, show_visible
    mov r0, r5                      @ placed before its image: a new widget is 0x0 at (0, 0), so its first damage rect is only
    mov r1, r7                      @ the picture's (setImage first made it 0,0 to the picture: black over the screen's lower left)
    mov r2, r8
    ldr r3, =IMG_POS
    blx r3
    mov r0, r5
    mov r1, r6
    ldr r3, =IMG_SET
    blx r3
    movs r1, #1
show_visible:
    str r1, [r5, #W_SHOWN]
    mov r0, r5
    ldr r3, =IMG_VISIBLE
    blx r3
    movs r0, #1
    strb r0, [r5, #(W_NODE + 0x24)] @ dirty: redrawn every paint, as the stock paint may have drawn over it
    mov r0, r4
    mov r1, r4
    mov r2, r5
    ldr r3, =IMG_ERASE
    blx r3
    mov r0, r4
    mov r1, r4
    mov r2, r5
    ldr r3, =IMG_DRAW
    blx r3
    ldr r3, =WIDGET_UNLOCK
    blx r3
show_out:
    pop {r4-r8, pc}

.thumb_func
text_width:                         @ r0 a string, r1 a font -> r0 its width in pixels (at most MAX_CHARS characters)
    push {r4, r5, lr}
    ldr r2, =GLYPHS
    movw r3, #GLYPHS_STEP
    mla r2, r1, r3, r2
    ldr r3, [r2]                    @ the spacing
    movs r4, #0
    movs r5, #MAX_CHARS
    cbz r0, width_done
width_char:
    ldrb r1, [r0], #1
    cbz r1, width_done
    and r1, r1, #0x7f
    add.w r1, r1, r1, lsl #1
    add.w r1, r2, r1, lsl #2
    ldr r1, [r1, #8]
    add r4, r1
    add r4, r3
    subs r5, #1
    bne width_char
width_done:
    cmp r4, #0
    it gt
    subgt r4, r3
    mov r0, r4
    pop {r4, r5, pc}

HXTRA_SETTING_GET
.ltorg
.balign 4
edit_pic:
    .space W_ANCHOR
    .word 4                         @ centred: a thin picture in the middle of the box
browser_pic:
    .space W_ANCHOR
    .word 4                         @ centred
row_short:                          @ a shortened name
    .space 20
