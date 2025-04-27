 OUTPUT_FORMAT("elf32-littlearm")
_region_min_align = 32;
MEMORY
    {
    FLASH (rx) : ORIGIN = 0x1000000, LENGTH = 0x40000
    RAM (wx) : ORIGIN = 0x21000000, LENGTH = 0x10000
    SRAM1 : ORIGIN = 553648128, LENGTH = 65536
    IDT_LIST (wx) : ORIGIN = 0xFFFF7FFF, LENGTH = 32K
    }
ENTRY("__start")
SECTIONS
    {
 .rel.plt :
 {
 *(.rel.plt)
 PROVIDE_HIDDEN (__rel_iplt_start = .);
 *(.rel.iplt)
 PROVIDE_HIDDEN (__rel_iplt_end = .);
 }
 .rela.plt :
 {
 *(.rela.plt)
 PROVIDE_HIDDEN (__rela_iplt_start = .);
 *(.rela.iplt)
 PROVIDE_HIDDEN (__rela_iplt_end = .);
 }
 .rel.dyn :
 {
 *(.rel.*)
 }
 .rela.dyn :
 {
 *(.rela.*)
 }
    /DISCARD/ :
 {
 *(.plt)
 }
    /DISCARD/ :
 {
 *(.iplt)
 }
   
 __rom_region_start = 0x1000000;
    rom_start :
 {
HIDDEN(__rom_start_address = .);
FILL(0x00);
. += 0x0 - (. - __rom_start_address);
. = ALIGN(4);
. = ALIGN( 1 << LOG2CEIL(4 * 32) );
. = ALIGN( 1 << LOG2CEIL(4 * (16 + 30)) );
_vector_start = .;
KEEP(*(.exc_vector_table))
KEEP(*(".exc_vector_table.*"))
KEEP(*(.vectors))
_vector_end = .;
. = ALIGN(4);
KEEP(*(.gnu.linkonce.irq_vector_table*))
 _vector_end = .;
 } > FLASH
    text :
 {
 __text_region_start = .;
 *(.text)
 *(".text.*")
 *(".TEXT.*")
 *(.gnu.linkonce.t.*)
 *(.glue_7t) *(.glue_7) *(.vfp11_veneer) *(.v4_bx)
 . = ALIGN(4);
 } > FLASH
 __text_region_end = .;
 .ARM.exidx :
 {
 __exidx_start = .;
 *(.ARM.exidx* gnu.linkonce.armexidx.*)
 __exidx_end = .;
 } > FLASH
 __rodata_region_start = .;
 initlevel :
 {
  __init_start = .;
  __init_EARLY_start = .; KEEP(*(SORT(.z_init_EARLY?_*))); KEEP(*(SORT(.z_init_EARLY??_*)));
  __init_PRE_KERNEL_1_start = .; KEEP(*(SORT(.z_init_PRE_KERNEL_1?_*))); KEEP(*(SORT(.z_init_PRE_KERNEL_1??_*)));
  __init_PRE_KERNEL_2_start = .; KEEP(*(SORT(.z_init_PRE_KERNEL_2?_*))); KEEP(*(SORT(.z_init_PRE_KERNEL_2??_*)));
  __init_POST_KERNEL_start = .; KEEP(*(SORT(.z_init_POST_KERNEL?_*))); KEEP(*(SORT(.z_init_POST_KERNEL??_*)));
  __init_APPLICATION_start = .; KEEP(*(SORT(.z_init_APPLICATION?_*))); KEEP(*(SORT(.z_init_APPLICATION??_*)));
  __init_SMP_start = .; KEEP(*(SORT(.z_init_SMP?_*))); KEEP(*(SORT(.z_init_SMP??_*)));
  __init_end = .;
  __deferred_init_list_start = .;
  KEEP(*(.z_deferred_init*))
  __deferred_init_list_end = .;
 } > FLASH
 device_area : SUBALIGN(4) { _device_list_start = .; KEEP(*(SORT(._device.static.*_?_*))); KEEP(*(SORT(._device.static.*_??_*))); _device_list_end = .; } > FLASH
 sw_isr_table :
 {
  . = ALIGN(4);
  *(.gnu.linkonce.sw_isr_table*)
 } > FLASH
 initlevel_error :
 {
  KEEP(*(SORT(.z_init_[_A-Z0-9]*)))
 }
 ASSERT(SIZEOF(initlevel_error) == 0, "Undefined initialization levels used.")
 app_shmem_regions : ALIGN_WITH_INPUT
 {
  __app_shmem_regions_start = .;
  KEEP(*(SORT(.app_regions.*)));
  __app_shmem_regions_end = .;
 } > FLASH
 k_p4wq_initparam_area : SUBALIGN(4) { _k_p4wq_initparam_list_start = .; KEEP(*(SORT_BY_NAME(._k_p4wq_initparam.static.*))); _k_p4wq_initparam_list_end = .; } > FLASH
 _static_thread_data_area : SUBALIGN(4) { __static_thread_data_list_start = .; KEEP(*(SORT_BY_NAME(.__static_thread_data.static.*))); __static_thread_data_list_end = .; } > FLASH
 device_deps : ALIGN_WITH_INPUT
 {
__device_deps_start = .;
KEEP(*(SORT(.__device_deps_pass2*)));
__device_deps_end = .;
 } > FLASH
ztest :
{
 _ztest_expected_result_entry_list_start = .; KEEP(*(SORT_BY_NAME(._ztest_expected_result_entry.static.*))); _ztest_expected_result_entry_list_end = .;
 _ztest_suite_node_list_start = .; KEEP(*(SORT_BY_NAME(._ztest_suite_node.static.*))); _ztest_suite_node_list_end = .;
 _ztest_unit_test_list_start = .; KEEP(*(SORT_BY_NAME(._ztest_unit_test.static.*))); _ztest_unit_test_list_end = .;
 _ztest_test_rule_list_start = .; KEEP(*(SORT_BY_NAME(._ztest_test_rule.static.*))); _ztest_test_rule_list_end = .;
} > FLASH
 init_array :
 {
  KEEP(*(SORT_BY_NAME(".ctors*")))
  KEEP(*(SORT_BY_NAME(".init_array*")))
 } > FLASH
 ASSERT (SIZEOF(init_array) == 0,
  "GNU-style constructors required but STATIC_INIT_GNU not enabled")
 bt_l2cap_fixed_chan_area : SUBALIGN(4) { _bt_l2cap_fixed_chan_list_start = .; KEEP(*(SORT_BY_NAME(._bt_l2cap_fixed_chan.static.*))); _bt_l2cap_fixed_chan_list_end = .; } > FLASH
 bt_conn_cb_area : SUBALIGN(4) { _bt_conn_cb_list_start = .; KEEP(*(SORT_BY_NAME(._bt_conn_cb.static.*))); _bt_conn_cb_list_end = .; } > FLASH
 bt_gatt_service_static_area : SUBALIGN(4) { _bt_gatt_service_static_list_start = .; KEEP(*(SORT_BY_NAME(._bt_gatt_service_static.static.*))); _bt_gatt_service_static_list_end = .; } > FLASH
 log_strings_area : SUBALIGN(4) { _log_strings_list_start = .; KEEP(*(SORT_BY_NAME(._log_strings.static.*))); _log_strings_list_end = .; } > FLASH
 log_const_area : SUBALIGN(4) { _log_const_list_start = .; KEEP(*(SORT_BY_NAME(._log_const.static.*))); _log_const_list_end = .; } > FLASH
 log_backend_area : SUBALIGN(4) { _log_backend_list_start = .; KEEP(*(SORT_BY_NAME(._log_backend.static.*))); _log_backend_list_end = .; } > FLASH
 log_link_area : SUBALIGN(4) { _log_link_list_start = .; KEEP(*(SORT_BY_NAME(._log_link.static.*))); _log_link_list_end = .; } > FLASH
 tracing_backend_area : SUBALIGN(4) { _tracing_backend_list_start = .; KEEP(*(SORT_BY_NAME(._tracing_backend.static.*))); _tracing_backend_list_end = .; } > FLASH
 zephyr_dbg_info : ALIGN_WITH_INPUT
 {
  KEEP(*(".dbg_thread_info"));
 } > FLASH
 intc_table_area : SUBALIGN(4) { _intc_table_list_start = .; KEEP(*(SORT_BY_NAME(._intc_table.static.*))); _intc_table_list_end = .; } > FLASH
 symbol_to_keep : ALIGN_WITH_INPUT
 {
  __symbol_to_keep_start = .;
  KEEP(*(SORT(.symbol_to_keep*)));
  __symbol_to_keep_end = .;
 } > FLASH
 shell_area : SUBALIGN(4) { _shell_list_start = .; KEEP(*(SORT_BY_NAME(._shell.static.*))); _shell_list_end = .; } > FLASH
 shell_root_cmds_area : SUBALIGN(4) { _shell_root_cmds_list_start = .; KEEP(*(SORT_BY_NAME(._shell_root_cmds.static.*))); _shell_root_cmds_list_end = .; } > FLASH
 shell_subcmds_area : SUBALIGN(4) { _shell_subcmds_list_start = .; KEEP(*(SORT_BY_NAME(._shell_subcmds.static.*))); _shell_subcmds_list_end = .; } > FLASH
 shell_dynamic_subcmds_area : SUBALIGN(4) { _shell_dynamic_subcmds_list_start = .; KEEP(*(SORT_BY_NAME(._shell_dynamic_subcmds.static.*))); _shell_dynamic_subcmds_list_end = .; } > FLASH
 cfb_font_area : SUBALIGN(4) { _cfb_font_list_start = .; KEEP(*(SORT_BY_NAME(._cfb_font.static.*))); _cfb_font_list_end = .; } > FLASH
 tdata : ALIGN_WITH_INPUT
 {
  *(.tdata .tdata.* .gnu.linkonce.td.*);
 } > FLASH
 tbss : ALIGN_WITH_INPUT
 {
  *(.tbss .tbss.* .gnu.linkonce.tb.* .tcommon);
 } > FLASH
 PROVIDE(__tdata_start = LOADADDR(tdata));
 PROVIDE(__tdata_align = ALIGNOF(tdata));
 PROVIDE(__tdata_size = (SIZEOF(tdata) + __tdata_align - 1) & ~(__tdata_align - 1));
 PROVIDE(__tdata_end = __tdata_start + __tdata_size);
 PROVIDE(__tbss_align = ALIGNOF(tbss));
 PROVIDE(__tbss_start = ADDR(tbss));
 PROVIDE(__tbss_size = (SIZEOF(tbss) + __tbss_align - 1) & ~(__tbss_align - 1));
 PROVIDE(__tbss_end = __tbss_start + __tbss_size);
 PROVIDE(__tls_start = __tdata_start);
 PROVIDE(__tls_end = __tbss_end);
 PROVIDE(__tls_size = __tbss_end - __tdata_start);
    rodata :
 {
 *(.rodata)
 *(".rodata.*")
 *(.gnu.linkonce.r.*)
 . = ALIGN(4);
 } > FLASH
 __rodata_region_end = .;
 . = ALIGN(_region_min_align);
 __rom_region_end = __rom_region_start + . - ADDR(rom_start);
   
    /DISCARD/ : {
 *(.got.plt)
 *(.igot.plt)
 *(.got)
 *(.igot)
 }
   
 . = 0x21000000;
 . = ALIGN(_region_min_align);
 _image_ram_start = .;
.ramfunc : ALIGN_WITH_INPUT
{
 . = ALIGN(_region_min_align);
 __ramfunc_start = .;
 *(.ramfunc)
 *(".ramfunc.*")
 . = ALIGN(_region_min_align);
 __ramfunc_end = .;
} > RAM AT > FLASH
__ramfunc_size = __ramfunc_end - __ramfunc_start;
__ramfunc_load_start = LOADADDR(.ramfunc);
   
    datas : ALIGN_WITH_INPUT
 {
 __data_region_start = .;
 __data_start = .;
 *(.data)
 *(".data.*")
 *(".kernel.*")
 __data_end = .;
 } > RAM AT > FLASH
    __data_size = __data_end - __data_start;
    __data_load_start = LOADADDR(datas);
    __data_region_load_start = LOADADDR(datas);
        device_states : ALIGN_WITH_INPUT
        {
                __device_states_start = .;
  KEEP(*(".z_devstate"));
  KEEP(*(".z_devstate.*"));
                __device_states_end = .;
        } > RAM AT > FLASH
 log_mpsc_pbuf_area : ALIGN_WITH_INPUT { _log_mpsc_pbuf_list_start = .; *(SORT_BY_NAME(._log_mpsc_pbuf.static.*)); _log_mpsc_pbuf_list_end = .; } > RAM AT > FLASH
 log_msg_ptr_area : ALIGN_WITH_INPUT { _log_msg_ptr_list_start = .; KEEP(*(SORT_BY_NAME(._log_msg_ptr.static.*))); _log_msg_ptr_list_end = .; } > RAM AT > FLASH
 log_dynamic_area : ALIGN_WITH_INPUT { _log_dynamic_list_start = .; KEEP(*(SORT_BY_NAME(._log_dynamic.static.*))); _log_dynamic_list_end = .; } > RAM AT > FLASH
 k_timer_area : ALIGN_WITH_INPUT { _k_timer_list_start = .; *(SORT_BY_NAME(._k_timer.static.*)); _k_timer_list_end = .; } > RAM AT > FLASH
 k_mem_slab_area : ALIGN_WITH_INPUT { _k_mem_slab_list_start = .; *(SORT_BY_NAME(._k_mem_slab.static.*)); _k_mem_slab_list_end = .; } > RAM AT > FLASH
 k_heap_area : ALIGN_WITH_INPUT { _k_heap_list_start = .; *(SORT_BY_NAME(._k_heap.static.*)); _k_heap_list_end = .; } > RAM AT > FLASH
 k_mutex_area : ALIGN_WITH_INPUT { _k_mutex_list_start = .; *(SORT_BY_NAME(._k_mutex.static.*)); _k_mutex_list_end = .; } > RAM AT > FLASH
 k_stack_area : ALIGN_WITH_INPUT { _k_stack_list_start = .; *(SORT_BY_NAME(._k_stack.static.*)); _k_stack_list_end = .; } > RAM AT > FLASH
 k_msgq_area : ALIGN_WITH_INPUT { _k_msgq_list_start = .; *(SORT_BY_NAME(._k_msgq.static.*)); _k_msgq_list_end = .; } > RAM AT > FLASH
 k_mbox_area : ALIGN_WITH_INPUT { _k_mbox_list_start = .; *(SORT_BY_NAME(._k_mbox.static.*)); _k_mbox_list_end = .; } > RAM AT > FLASH
 k_pipe_area : ALIGN_WITH_INPUT { _k_pipe_list_start = .; *(SORT_BY_NAME(._k_pipe.static.*)); _k_pipe_list_end = .; } > RAM AT > FLASH
 k_sem_area : ALIGN_WITH_INPUT { _k_sem_list_start = .; *(SORT_BY_NAME(._k_sem.static.*)); _k_sem_list_end = .; } > RAM AT > FLASH
 k_event_area : ALIGN_WITH_INPUT { _k_event_list_start = .; *(SORT_BY_NAME(._k_event.static.*)); _k_event_list_end = .; } > RAM AT > FLASH
 k_queue_area : ALIGN_WITH_INPUT { _k_queue_list_start = .; *(SORT_BY_NAME(._k_queue.static.*)); _k_queue_list_end = .; } > RAM AT > FLASH
 k_fifo_area : ALIGN_WITH_INPUT { _k_fifo_list_start = .; *(SORT_BY_NAME(._k_fifo.static.*)); _k_fifo_list_end = .; } > RAM AT > FLASH
 k_lifo_area : ALIGN_WITH_INPUT { _k_lifo_list_start = .; *(SORT_BY_NAME(._k_lifo.static.*)); _k_lifo_list_end = .; } > RAM AT > FLASH
 k_condvar_area : ALIGN_WITH_INPUT { _k_condvar_list_start = .; *(SORT_BY_NAME(._k_condvar.static.*)); _k_condvar_list_end = .; } > RAM AT > FLASH
 sys_mem_blocks_ptr_area : ALIGN_WITH_INPUT { _sys_mem_blocks_ptr_list_start = .; *(SORT_BY_NAME(._sys_mem_blocks_ptr.static.*)); _sys_mem_blocks_ptr_list_end = .; } > RAM AT > FLASH
 net_buf_pool_area : ALIGN_WITH_INPUT { _net_buf_pool_list_start = .; KEEP(*(SORT_BY_NAME(._net_buf_pool.static.*))); _net_buf_pool_list_end = .; } > RAM AT > FLASH
    __data_region_end = .;
   bss (NOLOAD) : ALIGN_WITH_INPUT
 {
        . = ALIGN(4);
 __bss_start = .;
 __kernel_ram_start = .;
 *(.bss)
 *(".bss.*")
 *(COMMON)
 *(".kernel_bss.*")
 __bss_end = ALIGN(4);
 } > RAM AT > RAM
    noinit (NOLOAD) :
        {
        *(.noinit)
        *(".noinit.*")
 *(".kernel_noinit.*")
        } > RAM AT > RAM
    __kernel_ram_end = 0x21000000 + 0x10000;
    __kernel_ram_size = __kernel_ram_end - __kernel_ram_start;
PROVIDE(soc_reset_hook = SystemInit);
.intList :
{
 KEEP(*(.irq_info*))
 KEEP(*(.intList*))
} > IDT_LIST
    .last_ram_section (NOLOAD) :
    {
 _image_ram_end = .;
 _image_ram_size = _image_ram_end - _image_ram_start;
 _end = .;
 z_mapped_end = .;
    } > RAM AT > RAM
   
 .stab 0 : { *(.stab) }
 .stabstr 0 : { *(.stabstr) }
 .stab.excl 0 : { *(.stab.excl) }
 .stab.exclstr 0 : { *(.stab.exclstr) }
 .stab.index 0 : { *(.stab.index) }
 .stab.indexstr 0 : { *(.stab.indexstr) }
 .gnu.build.attributes 0 : { *(.gnu.build.attributes .gnu.build.attributes.*) }
 .comment 0 : { *(.comment) }
 .debug 0 : { *(.debug) }
 .line 0 : { *(.line) }
 .debug_srcinfo 0 : { *(.debug_srcinfo) }
 .debug_sfnames 0 : { *(.debug_sfnames) }
 .debug_aranges 0 : { *(.debug_aranges) }
 .debug_pubnames 0 : { *(.debug_pubnames) }
 .debug_info 0 : { *(.debug_info .gnu.linkonce.wi.*) }
 .debug_abbrev 0 : { *(.debug_abbrev) }
 .debug_line 0 : { *(.debug_line .debug_line.* .debug_line_end ) }
 .debug_frame 0 : { *(.debug_frame) }
 .debug_str 0 : { *(.debug_str) }
 .debug_loc 0 : { *(.debug_loc) }
 .debug_macinfo 0 : { *(.debug_macinfo) }
 .debug_weaknames 0 : { *(.debug_weaknames) }
 .debug_funcnames 0 : { *(.debug_funcnames) }
 .debug_typenames 0 : { *(.debug_typenames) }
 .debug_varnames 0 : { *(.debug_varnames) }
 .debug_pubtypes 0 : { *(.debug_pubtypes) }
 .debug_ranges 0 : { *(.debug_ranges) }
 .debug_addr 0 : { *(.debug_addr) }
 .debug_line_str 0 : { *(.debug_line_str) }
 .debug_loclists 0 : { *(.debug_loclists) }
 .debug_macro 0 : { *(.debug_macro) }
 .debug_names 0 : { *(.debug_names) }
 .debug_rnglists 0 : { *(.debug_rnglists) }
 .debug_str_offsets 0 : { *(.debug_str_offsets) }
 .debug_sup 0 : { *(.debug_sup) }
    /DISCARD/ : { *(.note.GNU-stack) }
    .ARM.attributes 0 :
 {
 KEEP(*(.ARM.attributes))
 KEEP(*(.gnu.attributes))
 }
    SRAM1 (NOLOAD) : { __SRAM1_start = .; KEEP(*(SRAM1)) KEEP(*(SRAM1.*)) __SRAM1_end = .; } > SRAM1 __SRAM1_size = __SRAM1_end - __SRAM1_start; __SRAM1_load_start = LOADADDR(SRAM1);
.last_section :
{
  LONG(0xE015E015)
} > FLASH
_flash_used = LOADADDR(.last_section) + SIZEOF(.last_section) - __rom_region_start;
    }
