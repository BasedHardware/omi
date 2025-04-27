#ifndef _APP_VERSION_H_
#define _APP_VERSION_H_

/* The template values come from cmake/version.cmake
 * BUILD_VERSION related template values will be 'git describe',
 * alternatively user defined BUILD_VERSION.
 */

/* #undef ZEPHYR_VERSION_CODE */
/* #undef ZEPHYR_VERSION */

#define APPVERSION                   0x2010000
#define APP_VERSION_NUMBER           0x20100
#define APP_VERSION_MAJOR            2
#define APP_VERSION_MINOR            1
#define APP_PATCHLEVEL               0
#define APP_TWEAK                    0
#define APP_VERSION_STRING           "2.1.0-dev"
#define APP_VERSION_EXTENDED_STRING  "2.1.0-dev+0"
#define APP_VERSION_TWEAK_STRING     "2.1.0+0"

#define APP_BUILD_VERSION v2.1.0-ncs3-1


#endif /* _APP_VERSION_H_ */
