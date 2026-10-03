/* custom_test_hook.c — Custom MIDI Velocity Processing Hook */
extern int midi_slot_is_active(int slot);

int custom_velocity_curve(int velocity) {
    if (velocity <= 0) return 0;
    if (velocity >= 120) return 127;
    // Exponential curve transformation
    return (velocity * velocity) / 127;
}

int custom_midi_handler(int status, int note, int vel) {
    if ((status & 0xF0) == 0x90 && vel > 0) {
        vel = custom_velocity_curve(vel);
    }
    return (vel << 16) | (note << 8) | status;
}
