#ifndef _KERNEL_VERSION_H_
#define _KERNEL_VERSION_H_

/* The template values come from cmake/version.cmake
 * BUILD_VERSION related template values will be 'git describe',
 * alternatively user defined BUILD_VERSION.
 */

#define ZEPHYR_VERSION_CODE 198499
#define ZEPHYR_VERSION(a,b,c) (((a) << 16) + ((b) << 8) + (c))

#define KERNELVERSION                   0x3076300
#define KERNEL_VERSION_NUMBER           0x30763
#define KERNEL_VERSION_MAJOR            3
#define KERNEL_VERSION_MINOR            7
#define KERNEL_PATCHLEVEL               99
#define KERNEL_TWEAK                    0
#define KERNEL_VERSION_STRING           "3.7.99"
#define KERNEL_VERSION_EXTENDED_STRING  "3.7.99+0"
#define KERNEL_VERSION_TWEAK_STRING     "3.7.99+0"

#define BUILD_VERSION v3.7.99-ncs2


#endif /* _KERNEL_VERSION_H_ */
