type EventHandler = (...args: any[]) => void;

class EventBus {
    private events: { [eventName: string]: EventHandler[] };

    constructor() {
        this.events = {};
    }

    public on(eventName: string, handler: EventHandler): void {
        if (!this.events[eventName]) {
            this.events[eventName] = [];
        }
        this.events[eventName].push(handler);
    }

    public off(eventName: string, handler: EventHandler): void {
        const eventHandlers = this.events[eventName];
        if (eventHandlers) {
            this.events[eventName] = eventHandlers.filter(h => h !== handler);
        }
    }

    public emit(eventName: string, ...args: any[]): void {
        const eventHandlers = this.events[eventName];
        if (eventHandlers) {
            eventHandlers.forEach(handler => handler(...args));
        }
    }
}

export const eventBus = new EventBus();