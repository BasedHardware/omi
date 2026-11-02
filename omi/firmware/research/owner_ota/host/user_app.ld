ENTRY(reset)
MEMORY {
  FLASH (rx) : ORIGIN = 0x54200, LENGTH = 0x5fe00
  RAM (rw) : ORIGIN = 0x20012000, LENGTH = 0x5e000
}
SECTIONS {
 .vectors : { KEEP(*(.vectors)) . = ORIGIN(FLASH) + 512; } > FLASH
 .text : { *(.text*) *(.rodata*) } > FLASH
 .data : { *(.data*) } > RAM AT > FLASH
 .bss (NOLOAD) : { *(.bss*) *(COMMON) } > RAM
 /DISCARD/ : { *(.comment) *(.note*) }
}
