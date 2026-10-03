extern int midi_slot_is_active(int slot);

int custom_check_slot(int slot) {
    if (slot < 0) return 0;
    return midi_slot_is_active(slot);
}
