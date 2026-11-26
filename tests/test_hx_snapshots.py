"""tools/hx_snapshots.py: the request's map and order, the read's decoding, and the checks, against a fake editor stream."""
import msgpack
import pytest

import hx_snapshots as hs
import usb_commands


def entry(exists, colour, named, name):
    return bytes([exists, colour, named]) + name.ljust(11, b'\0')


READ = (entry(1, 2, 1, b'LEAD') + entry(1, 4, 1, b'VERSE') + entry(1, 8, 1, b'CHORUS')
        + entry(1, 9, 1, b'CHORUS 2') + entry(1, 6, 1, b'VERSE 2') + entry(1, 10, 1, b'ELEVENCHARS') + bytes([1, 2, 1]))


class Editor:
    """hx_ctl's editor stream: records each request as packed, answers a read with READ."""

    def __init__(self, reply=READ):
        self.sent, self.reply = [], reply

    def request(self, cmd, params=None):
        self.sent.append((cmd, msgpack.packb(params, use_bin_type=False)))
        return self.reply if params[hs.K_INDEX] == hs.READ_ALL else None


def test_the_command_is_more_snapshots_line():
    assert hs.CMD == usb_commands.by_feature()['more_snapshots'] == 0x50


def test_a_write_sends_the_name_before_the_colour():
    """[verified on unit] the firmware's read of the name clears the colour's byte, so the name goes first."""
    ed = Editor()
    hs.write(ed, 5, 'Solo', 'red')
    assert ed.sent == [(0x50, bytes([0x83, 0x5c, 4, 0x6d, 0xa4]) + b'Solo' + bytes([0x42, 2]))]


def test_a_read_sends_index_6_with_every_key():
    ed = Editor()
    hs.read(ed)
    assert ed.sent == [(0x50, bytes([0x83, 0x5c, 6, 0x6d, 0xa0, 0x42, 0]))]


def test_a_read_decodes_the_six_and_where_the_unit_is():
    state = hs.read(Editor())
    assert [(s['number'], s['name'], s['colour']) for s in state['snapshots']] == [
        (1, 'LEAD', 2), (2, 'VERSE', 4), (3, 'CHORUS', 8), (4, 'CHORUS 2', 9), (5, 'VERSE 2', 6), (6, 'ELEVENCHARS', 10)]
    assert all(s['exists'] and s['named'] for s in state['snapshots'])
    assert (state['live_bank'], state['current'], state['has_bank_b']) == (1, 5, True), 'bank B live, its third: snapshot 6'


def test_a_preset_without_bank_b_reads_4_to_6_as_none():
    blob = READ[:3 * hs.ENTRY] + bytes(3 * hs.ENTRY) + bytes([0, 0, 0])
    state = hs.decode(blob)
    assert [s['exists'] for s in state['snapshots']] == [True] * 3 + [False] * 3 and not state['has_bank_b']


def test_a_reply_of_another_length_is_not_this_command():
    with pytest.raises(hs.SnapshotError):
        hs.decode(b'\xc0')


@pytest.mark.parametrize('name', ['ELEVENCHARS', 'Café', 'tab\there', 7])
def test_a_name_the_unit_cannot_show_is_refused_before_sending(name):
    ed = Editor()
    with pytest.raises(hs.SnapshotError):
        hs.write(ed, 1, name, 0)
    assert ed.sent == []


@pytest.mark.parametrize('colour, number', [(0, 0), (11, 11), ('Turquoise', 7), ('dark orange', 3)])
def test_colours_by_number_or_name(colour, number):
    assert hs.colour_number(colour) == number


@pytest.mark.parametrize('colour', [12, -1, 'Teal'])
def test_other_colours_are_refused(colour):
    with pytest.raises(hs.SnapshotError):
        hs.colour_number(colour)


@pytest.mark.parametrize('number', [0, 7])
def test_snapshots_are_1_to_6(number):
    with pytest.raises(hs.SnapshotError):
        hs.write(Editor(), number, 'A', 0)
