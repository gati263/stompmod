"""The SHARC primitives the patchers may take for a kernel of their own: none that stock audio runs through."""
import kit_patch_amp
import patch_amp

IO_WRITERS = (0x2aa8, 0x2aaa, 0x2aab, 0x2aac)   # phones, Send, Main, USB out [verified on unit, docs/research/sharc/usb-routing.md]
ROOT_GRAPH = (0x261a, 0x238f)


def test_the_two_lists_agree():
    assert patch_amp.UNUSED_SHARC_PRIMS == kit_patch_amp.UNUSED_SHARC_PRIMS


def test_no_live_primitive_is_offered():
    ids = {pid for pid, _ in patch_amp.UNUSED_SHARC_PRIMS}
    assert not ids & set(IO_WRITERS + ROOT_GRAPH)


def test_rows_are_registry_rows():
    for pid, row in patch_amp.UNUSED_SHARC_PRIMS:
        assert 0x200000 <= row < 0x200610 and row % 8 == 0, f'{pid:#x}: {row:#x}'
