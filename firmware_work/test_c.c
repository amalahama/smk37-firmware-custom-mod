int custom_midi_filter(int msg) {
    int cmd = msg & 0xF0;
    if (cmd == 0x90) {
        return msg | 0x01;
    }
    return msg;
}
