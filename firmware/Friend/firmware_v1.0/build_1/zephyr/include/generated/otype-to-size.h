/* Non device/stack objects */
case K_OBJ_MEM_SLAB: ret = sizeof(struct k_mem_slab); break;
case K_OBJ_MSGQ: ret = sizeof(struct k_msgq); break;
case K_OBJ_MUTEX: ret = sizeof(struct k_mutex); break;
case K_OBJ_PIPE: ret = sizeof(struct k_pipe); break;
case K_OBJ_QUEUE: ret = sizeof(struct k_queue); break;
case K_OBJ_POLL_SIGNAL: ret = sizeof(struct k_poll_signal); break;
case K_OBJ_SEM: ret = sizeof(struct k_sem); break;
case K_OBJ_STACK: ret = sizeof(struct k_stack); break;
case K_OBJ_THREAD: ret = sizeof(struct k_thread); break;
case K_OBJ_TIMER: ret = sizeof(struct k_timer); break;
case K_OBJ_CONDVAR: ret = sizeof(struct k_condvar); break;
#ifdef CONFIG_EVENTS
case K_OBJ_EVENT: ret = sizeof(struct k_event); break;
#endif
