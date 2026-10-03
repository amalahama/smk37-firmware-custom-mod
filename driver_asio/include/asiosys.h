#ifndef __asiosys__
#define __asiosys__

#ifdef _WIN32
    #define IEEE754_64FLOAT 1
    #define NATIVE_INT64 1
    typedef long long ASIOInt64;
    typedef unsigned long long ASIOUInt64;
    #define ASIO_LITTLE_ENDIAN 1
#endif

#endif // __asiosys__
