export interface Memory {
  id: string;
  created_at: Date;
  started_at: Date;
  finished_at: Date;
  source: string;
  language: string;
  structured: Structured;
  transcript_segments: any[];
  geolocation: Geolocation;
  photos: any[];
  plugins_results: any[];
  external_data: ExternalData;
  postprocessing: Postprocessing;
  discarded: boolean;
  deleted: boolean;
}

export interface ExternalData {}

export interface Geolocation {
  google_place_id: string;
  latitude: number;
  longitude: number;
  address: string;
  location_type: string;
}

export interface Postprocessing {
  status: string;
  model: string;
}

export interface Structured {
  title: string;
  overview: string;
  emoji: string;
  category: string;
  action_items: any[];
  events: any[];
}
