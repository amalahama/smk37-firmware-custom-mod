#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <stdio.h>

int main() {
    GUID g1 = __uuidof(MMDeviceEnumerator);
    GUID g2 = __uuidof(IMMDeviceEnumerator);
    GUID g3 = __uuidof(IAudioClient);
    GUID g4 = __uuidof(IAudioRenderClient);
    printf("MMDeviceEnumerator: %08lX\n", (unsigned long)g1.Data1);
    printf("IMMDeviceEnumerator: %08lX\n", (unsigned long)g2.Data1);
    printf("IAudioClient: %08lX\n", (unsigned long)g3.Data1);
    printf("IAudioRenderClient: %08lX\n", (unsigned long)g4.Data1);
    return 0;
}
