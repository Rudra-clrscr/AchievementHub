import {
  certificatesApi,
  eventsApi,
  internshipsApi,
  patentsApi,
  publicationsApi,
  type UploadCategory,
} from "./api/client";
import type { AchievementApi, FieldConfig } from "./components/AchievementSection";

export interface AchievementTypeConfig {
  key: UploadCategory;
  label: string;
  idKey: string;
  fields: FieldConfig[];
  api: AchievementApi;
}

const CATEGORIES = ["FDP", "external", "NPTEL", "IEEE"];

export const ACHIEVEMENT_TYPES: AchievementTypeConfig[] = [
  {
    key: "certificates",
    label: "Certificates",
    idKey: "cert_id",
    api: certificatesApi,
    fields: [
      { name: "title", label: "Title", type: "text", required: true },
      { name: "issuer", label: "Issuer", type: "text" },
      { name: "category", label: "Category", type: "select", options: CATEGORIES, required: true },
    ],
  },
  {
    key: "publications",
    label: "Publications",
    idKey: "pub_id",
    api: publicationsApi,
    fields: [
      { name: "title", label: "Title", type: "text", required: true },
      { name: "venue", label: "Venue/Journal", type: "text" },
      { name: "publication_date", label: "Publication date", type: "date" },
    ],
  },
  {
    key: "patents",
    label: "Patents",
    idKey: "patent_id",
    api: patentsApi,
    fields: [
      { name: "title", label: "Title", type: "text", required: true },
      { name: "patent_number", label: "Patent number", type: "text" },
      { name: "filing_date", label: "Filing date", type: "date" },
    ],
  },
  {
    key: "internships",
    label: "Internships",
    idKey: "internship_id",
    api: internshipsApi,
    fields: [
      { name: "organization", label: "Organization", type: "text", required: true },
      { name: "role_title", label: "Role", type: "text" },
      { name: "start_date", label: "Start date", type: "date" },
      { name: "end_date", label: "End date", type: "date" },
    ],
  },
  {
    key: "events",
    label: "Event Participation",
    idKey: "event_id",
    api: eventsApi,
    fields: [
      { name: "event_name", label: "Event name", type: "text", required: true },
      { name: "event_date", label: "Event date", type: "date" },
      { name: "participation_role", label: "Role", type: "select", options: ["participant", "organizer"] },
    ],
  },
];
