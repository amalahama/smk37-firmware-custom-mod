data = open("firmware_work/v16_unpacked/files/app.bin", "rb").read()

print("Before cave 1 (0x967E0..0x967F5):")
print(data[0x967E0:0x96800])

print("After cave 1 (0x967F1 + 1449 = 0x96DA0):")
print(data[0x96D90:0x96DB0])

# Check if 0x02096800 is 4-byte or 16-byte aligned
cave_addr = 0x02096800
cave_offset = cave_addr - 0x02000000
print(f"Aligned cave address: 0x{cave_addr:08X} (offset 0x{cave_offset:06X})")
print(f"Cave available size from 0x{cave_offset:06X} to 0x096DA0: {0x096DA0 - cave_offset} bytes")
