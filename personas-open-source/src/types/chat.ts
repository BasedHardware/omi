type Message = {
    id: number;
    text: string;
    sender: 'user' | 'omi';
    type: 'text';
    status?: 'sending' | 'sent' | 'received';
  };
  
  export type { Message };