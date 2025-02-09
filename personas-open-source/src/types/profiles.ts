/**
 * @fileoverview Type definitions for social media profiles and chatbots
 * @description Contains type interfaces for Twitter profiles, LinkedIn profiles, and chatbot data
 * @author HarshithSunku
 * @license MIT
 */

/**
 * Chatbot type definition
 * @description Represents a chatbot persona created from social media profiles
 */
export type Chatbot = {
  id: string;
  username?: string;
  profile?: string;
  avatar: string;
  desc: string;
  name: string;
  sub_count?: number;
  category: string;
  created_at?: string;
  verified?: boolean;
  connection_count?: number;
};

/**
 * Twitter Profile type definition
 * @description Represents Twitter user profile data
 */
export type TwitterProfile = {
  profile: string;
  rest_id: string;
  avatar: string;
  desc: string;
  name: string;
  friends: number;
  sub_count: number;
  id: string;
};

/**
 * LinkedIn Profile type definition
 * @description Represents comprehensive LinkedIn user profile and posts data
 * @property {number} connection - Number of LinkedIn connections 
 * @property {Object} data - Core profile information including personal details, experience, education
 * @property {number} follower - Number of LinkedIn followers
 * @property {Array} posts - Array of LinkedIn posts with engagement metrics
 */
export type LinkedinProfile = {
  connection: number;
  data: {
    id: number;
    urn: string;
    username: string;
    firstName: string;
    lastName: string;
    isTopVoice: boolean;
    isCreator: boolean;
    profilePicture: string;
    backgroundImage: { width: number; height: number; url: string }[];
    summary: string;
    headline: string;
    geo: { country: string; city: string; full: string; countryCode: string };
    educations: {
      start: { year: number; month: number; day: number };
      end: { year: number; month: number; day: number };
      fieldOfStudy: string;
      degree: string;
      grade: string;
      schoolName: string;
      description: string;
      activities: string;
      url: string;
      schoolId: string;
      logo: { url: string; width: number; height: number }[];
    }[];
    position: {
      companyId: number;
      companyName: string;
      companyUsername: string;
      companyURL: string;
      companyLogo: string;
      companyIndustry: string;
      companyStaffCountRange: string;
      title: string;
      multiLocaleTitle: { en_US: string };
      multiLocaleCompanyName: { en_US: string };
      location: string;
      description: string;
      employmentType: string;
      start: { year: number; month: number; day: number };
      end: { year: number; month: number; day: number };
    }[];
    fullPositions: {
      companyId: number;
      companyName: string;
      companyUsername: string;
      companyURL: string;
      companyLogo: string;
      companyIndustry: string;
      companyStaffCountRange: string;
      title: string;
      multiLocaleTitle: { en_US: string };
      multiLocaleCompanyName: { en_US: string };
      location: string;
      description: string;
      employmentType: string;
      start: { year: number; month: number; day: number };
      end: { year: number; month: number; day: number };
    }[];
    skills: { name: string; passedSkillAssessment: boolean; endorsementsCount: number }[];
    projects: Record<string, unknown>;
    supportedLocales: { country: string; language: string }[];
    multiLocaleFirstName: { en: string };
    multiLocaleLastName: { en: string };
    multiLocaleHeadline: { en: string };
  };
  follower: number;
  posts: {
    isBrandPartnership: boolean;
    text: string;
    totalReactionCount: number;
    likeCount: number;
    appreciationCount: number;
    empathyCount: number;
    InterestCount: number;
    praiseCount: number;
    commentsCount: number;
    repostsCount: number;
    postUrl: string;
    postedAt: string;
    postedDate: string;
    postedDateTimestamp: number;
    urn: string;
    author: {
      firstName: string;
      lastName: string;
      username: string;
      url: string;
    };
    company: Record<string, unknown>;
    document: Record<string, unknown>;
    celebration: Record<string, unknown>;
    poll: Record<string, unknown>;
    article: {
      articleUrn: string;
      title: string;
      subtitle: string;
      link: string;
      newsletter: Record<string, unknown>;
    };
    entity: Record<string, unknown>;
    mentions: {
      firstName: string;
      lastName: string;
      urn: string;
      publicIdentifier: string;
    }[];
    companyMentions: {
      id: number;
      name: string;
      publicIdentifier: string;
      url: string;
    }[];
  }[];
};  
