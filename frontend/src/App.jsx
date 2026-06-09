import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { HiMenuAlt1 } from "react-icons/hi";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";
import {
  faArrowUp,
  faChevronUp,
  faCrosshairs,
  faChevronDown,
  faEllipsis,
  faEnvelope,
  faFile,
  faFileArrowUp,
  faCheck,
  faCalendarDays,
  faCircleQuestion,
  faMagnifyingGlass,
  faPaperPlane,
  faPenToSquare,
  faPlus,
  faRightToBracket,
  faStop,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";
import loadingAnimation from "../lottie/Loading Animation.json";

const API_BASE = import.meta.env.VITE_API_BASE || (import.meta.env.DEV ? "http://localhost:8000" : "");
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const SCHEDULE_DAYS = [
  { key: "mon", label: "Mon" },
  { key: "tue", label: "Tue" },
  { key: "wed", label: "Wed" },
  { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" },
  { key: "sat", label: "Sat" },
  { key: "sun", label: "Sun" },
];
const DEFAULT_SCHEDULE = {
  enabled: false,
  time: "09:00",
  timezone: getBrowserTimeZone(),
  days: {
    mon: true,
    tue: true,
    wed: true,
    thu: true,
    fri: true,
    sat: false,
    sun: false,
  },
  keywords: "",
  location: "United States",
  pages: 1,
  email_to: "",
};
const INTRO_SEARCH_SUGGESTIONS = [
  "Search for jobs in California",
  "Look for mobile development jobs at Google",
  "Find product design roles in New York",
  "Search for data analyst jobs in Chicago",
  "Look for remote frontend jobs",
  "Find machine learning jobs at startups",
  "Search for cybersecurity roles in Texas",
  "Look for backend engineering jobs in Seattle",
  "Find frontend roles at startups",
  "Look for backend jobs in Austin",
  "Search for data science roles in New York",
  "Find product manager jobs in San Francisco",
  "Look for remote DevOps roles",
  "Search for cybersecurity jobs at Microsoft",
  "Find QA engineering jobs in Chicago",
  "Look for iOS development jobs at Apple",
  "Search for machine learning jobs in Seattle",
];
const INTRO_SUGGESTION_ROTATE_MS = 15000;
const INTRO_SUGGESTION_FADE_MS = 220;
const FETCHING_FALLBACK_WORDS = [
  "Rummaging",
  "Inquiring",
  "Sifting",
  "Dusting for Leads",
  "Tracking",
  "Searching",
  "Fetching",
];

function normalizeSchedulePagesInput(value) {
  const trimmedValue = String(value || "").trim();
  const parsedValue = Number(trimmedValue);
  if (!Number.isFinite(parsedValue)) {
    return "";
  }
  return String(Math.min(4, Math.max(1, Math.trunc(parsedValue))));
}

function getRandomIntroSuggestion(exclude = "") {
  if (INTRO_SEARCH_SUGGESTIONS.length === 0) {
    return "";
  }
  if (INTRO_SEARCH_SUGGESTIONS.length === 1) {
    return INTRO_SEARCH_SUGGESTIONS[0];
  }

  const filtered = INTRO_SEARCH_SUGGESTIONS.filter((suggestion) => suggestion !== exclude);
  const pool = filtered.length > 0 ? filtered : INTRO_SEARCH_SUGGESTIONS;
  return pool[Math.floor(Math.random() * pool.length)];
}

function getRandomFetchingFallback(exclude = "") {
  if (FETCHING_FALLBACK_WORDS.length === 0) {
    return "";
  }
  if (FETCHING_FALLBACK_WORDS.length === 1) {
    return FETCHING_FALLBACK_WORDS[0];
  }

  const filtered = FETCHING_FALLBACK_WORDS.filter((word) => word !== exclude);
  const pool = filtered.length > 0 ? filtered : FETCHING_FALLBACK_WORDS;
  return pool[Math.floor(Math.random() * pool.length)];
}

function getSessionId() {
  const storageKey = "job_hunting_agent_session_id";
  try {
    const existing = window.sessionStorage.getItem(storageKey);
    if (existing) return existing;
    const created = crypto.randomUUID();
    window.sessionStorage.setItem(storageKey, created);
    return created;
  } catch {
    return crypto.randomUUID();
  }
}

function createSessionId() {
  const storageKey = "job_hunting_agent_session_id";
  const created = crypto.randomUUID();
  try {
    window.sessionStorage.setItem(storageKey, created);
  } catch {
    // Ignore storage failures and fall back to the in-memory ID.
  }
  return created;
}

function getBrowserTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function setViewportHeightVariable() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }
  const viewportHeight = window.visualViewport?.height || window.innerHeight;
  const layoutViewportHeight = window.innerHeight;
  document.documentElement.style.setProperty("--vh", `${viewportHeight * 0.01}px`);
  document.documentElement.style.setProperty("--app-vh", `${layoutViewportHeight * 0.01}px`);
}

const WEEKDAY_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
const WEEKDAY_LABEL_TO_INDEX = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};

function parseTimeString(timeString) {
  const [hourText, minuteText] = String(timeString || "00:00").split(":");
  return {
    hour: Number(hourText) || 0,
    minute: Number(minuteText) || 0,
  };
}

function formatTimeString(hour, minute) {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function getZoneDateParts(date, timeZone) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour12: false,
    hourCycle: "h23",
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(date);

  const mapped = {};
  for (const part of parts) {
    if (part.type !== "literal") {
      mapped[part.type] = part.value;
    }
  }

  return {
    year: Number(mapped.year),
    month: Number(mapped.month),
    day: Number(mapped.day),
    hour: Number(mapped.hour),
    minute: Number(mapped.minute),
    weekdayIndex: WEEKDAY_LABEL_TO_INDEX[mapped.weekday] ?? 0,
  };
}

function getTimeZoneOffset(date, timeZone) {
  const parts = getZoneDateParts(date, timeZone);
  const asUTC = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, 0);
  return asUTC - date.getTime();
}

function zonedTimeToUtc(year, month, day, hour, minute, timeZone) {
  const utcGuess = new Date(Date.UTC(year, month - 1, day, hour, minute, 0));
  const firstOffset = getTimeZoneOffset(utcGuess, timeZone);
  let adjusted = new Date(utcGuess.getTime() - firstOffset);
  const secondOffset = getTimeZoneOffset(adjusted, timeZone);
  if (secondOffset !== firstOffset) {
    adjusted = new Date(utcGuess.getTime() - secondOffset);
  }
  return adjusted;
}

function convertScheduleForViewer(payload, sourceTimeZone, targetTimeZone) {
  const safeSourceZone = sourceTimeZone || targetTimeZone || getBrowserTimeZone();
  const safeTargetZone = targetTimeZone || getBrowserTimeZone();
  const sourceTime = parseTimeString(payload?.time || DEFAULT_SCHEDULE.time);
  const sourceDays = payload?.days || {};

  if (safeSourceZone === safeTargetZone) {
    return {
      enabled: Boolean(payload?.enabled),
      time: formatTimeString(sourceTime.hour, sourceTime.minute),
      timezone: safeTargetZone,
      days: {
        mon: Boolean(sourceDays.mon),
        tue: Boolean(sourceDays.tue),
        wed: Boolean(sourceDays.wed),
        thu: Boolean(sourceDays.thu),
        fri: Boolean(sourceDays.fri),
        sat: Boolean(sourceDays.sat),
        sun: Boolean(sourceDays.sun),
      },
      keywords: String(payload?.keywords || DEFAULT_SCHEDULE.keywords),
      location: String(payload?.location || DEFAULT_SCHEDULE.location),
      pages: Number(payload?.pages || DEFAULT_SCHEDULE.pages),
      email_to: String(payload?.email_to || DEFAULT_SCHEDULE.email_to),
    };
  }

  const sourceNow = getZoneDateParts(new Date(), safeSourceZone);
  const currentSourceCalendar = new Date(Date.UTC(sourceNow.year, sourceNow.month - 1, sourceNow.day));
  const weekStart = new Date(currentSourceCalendar);
  weekStart.setUTCDate(currentSourceCalendar.getUTCDate() - currentSourceCalendar.getUTCDay());

  const convertedDays = {
    mon: false,
    tue: false,
    wed: false,
    thu: false,
    fri: false,
    sat: false,
    sun: false,
  };

  let convertedTime = formatTimeString(sourceTime.hour, sourceTime.minute);
  let convertedTimeSet = false;

  WEEKDAY_KEYS.forEach((dayKey, dayIndex) => {
    if (!sourceDays[dayKey]) return;
    const selectedCalendar = new Date(weekStart);
    selectedCalendar.setUTCDate(weekStart.getUTCDate() + dayIndex);
    const utcInstant = zonedTimeToUtc(
      selectedCalendar.getUTCFullYear(),
      selectedCalendar.getUTCMonth() + 1,
      selectedCalendar.getUTCDate(),
      sourceTime.hour,
      sourceTime.minute,
      safeSourceZone,
    );
    const targetParts = getZoneDateParts(utcInstant, safeTargetZone);
    const targetDayKey = WEEKDAY_KEYS[targetParts.weekdayIndex];
    convertedDays[targetDayKey] = true;
    if (!convertedTimeSet) {
      convertedTime = formatTimeString(targetParts.hour, targetParts.minute);
      convertedTimeSet = true;
    }
  });

  return {
    enabled: Boolean(payload?.enabled),
    time: convertedTime,
    timezone: safeTargetZone,
    days: convertedDays,
    keywords: String(payload?.keywords || DEFAULT_SCHEDULE.keywords),
    location: String(payload?.location || DEFAULT_SCHEDULE.location),
    pages: Number(payload?.pages || DEFAULT_SCHEDULE.pages),
    email_to: String(payload?.email_to || DEFAULT_SCHEDULE.email_to),
  };
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof payload === "object" ? payload.detail : payload;
    throw new Error(detail || "Request failed");
  }

  return payload;
}

function SafeLottie({ animationData, className }) {
  const mountRef = useRef(null);

  useEffect(() => {
    let anim = null;
    let cancelled = false;

    async function load() {
      if (!mountRef.current) return;
      try {
        const lottieModule = await import("lottie-web");
        if (cancelled || !mountRef.current) return;
        const lottie = lottieModule.default || lottieModule;
        anim = lottie.loadAnimation({
          container: mountRef.current,
          renderer: "svg",
          loop: true,
          autoplay: true,
          animationData,
        });
      } catch {
        // Prevent UI crash if lottie fails to initialize.
      }
    }

    load();
    return () => {
      cancelled = true;
      if (anim) anim.destroy();
    };
  }, [animationData]);

  return <div ref={mountRef} className={className} aria-hidden="true" />;
}

function JobCard({ job, isMobileLayout }) {
  const score = Math.max(0, Math.min(100, Number(job.score || 0) || 0));
  const [scoreHovered, setScoreHovered] = useState(false);
  const [scoreExpanded, setScoreExpanded] = useState(isMobileLayout);
  const scoreHoverTimerRef = useRef(null);
  const recommendationMap = {
    apply: "Apply",
    apply_today: "Apply",
    review: "Review",
    maybe: "Maybe",
    ignore: "Ignore",
  };
  const recommendation = recommendationMap[job.recommendation] || job.recommendation || "";
  const isTopScore = score === 100;
  const isExpandedScore = scoreHovered || scoreExpanded;
  const recommendationTone = ({
    apply: "apply",
    apply_today: "apply",
    review: "review",
    maybe: "maybe",
    ignore: "ignore",
  })[String(job.recommendation || "").toLowerCase()] || "";
  const scheduleScoreHover = () => {
    if (scoreHoverTimerRef.current) {
      clearTimeout(scoreHoverTimerRef.current);
    }
    scoreHoverTimerRef.current = setTimeout(() => {
      setScoreHovered(true);
      scoreHoverTimerRef.current = null;
    }, 100);
  };
  const cancelScoreHover = () => {
    if (scoreHoverTimerRef.current) {
      clearTimeout(scoreHoverTimerRef.current);
      scoreHoverTimerRef.current = null;
    }
    setScoreHovered(false);
  };

  useEffect(() => {
    if (isMobileLayout) {
      if (scoreHoverTimerRef.current) {
        clearTimeout(scoreHoverTimerRef.current);
        scoreHoverTimerRef.current = null;
      }
      setScoreHovered(false);
      setScoreExpanded(true);
      return undefined;
    }
    setScoreExpanded(false);
    setScoreHovered(false);
    if (scoreHoverTimerRef.current) {
      clearTimeout(scoreHoverTimerRef.current);
      scoreHoverTimerRef.current = null;
    }
    return undefined;
  }, [isMobileLayout]);

  useEffect(
    () => () => {
      if (scoreHoverTimerRef.current) {
        clearTimeout(scoreHoverTimerRef.current);
      }
    },
    [],
  );

  return (
    <article className="job-card">
      <div className="job-card-header">
        <div className="job-card-title-group">
          <h4>{job.title || "Untitled role"}</h4>
          <div className="job-card-meta-inline">
            <p className="job-meta">{job.company || "Unknown company"}</p>
            <span className="job-card-meta-separator" aria-hidden="true">•</span>
            <p className="job-meta">{job.location || "Unknown location"}</p>
          </div>
        </div>
        <div
          className={`job-score-pill ${isMobileLayout ? "mobile-toggle" : ""} ${isExpandedScore ? "hovered" : ""}`}
          aria-label={`Score ${score} out of 100`}
          role={isMobileLayout ? "button" : undefined}
          tabIndex={isMobileLayout ? 0 : undefined}
          style={{ "--score-percent": score }}
          onMouseEnter={isMobileLayout ? undefined : scheduleScoreHover}
          onMouseLeave={isMobileLayout ? undefined : cancelScoreHover}
          onClick={
            isMobileLayout
              ? () => {
                  setScoreExpanded((value) => !value);
                }
              : undefined
          }
          onKeyDown={
            isMobileLayout
              ? (event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setScoreExpanded((value) => !value);
                  }
                }
              : undefined
          }
          >
          <span className="job-score-inline">
            <span className={`job-score-value ${isTopScore && isExpandedScore ? "is-hundred" : ""}`}>{score}</span>
            <span className="job-score-total">/100</span>
          </span>
          <span className="job-score-hover-content" aria-hidden="true">
            <span className="job-score-circle">
              <span className={`job-score-centered ${recommendationTone ? `tone-${recommendationTone}` : ""} ${isTopScore && isExpandedScore ? "is-hundred" : ""}`}>{score}</span>
              <svg className="job-score-ring" viewBox="0 0 36 36" focusable="false">
                <circle className={`job-score-ring-progress ${isTopScore ? "is-hundred" : ""}`} cx="18" cy="18" r="14" />
              </svg>
            </span>
            <span className="job-score-recommendation">{recommendation}</span>
          </span>
        </div>
      </div>
      <p className="job-fit">{job.fit_summary || "No summary provided."}</p>
      <a className="job-link" href={job.url} target="_blank" rel="noreferrer">Open listing</a>
    </article>
  );
}

function ReportPanel({ report, onEmailLatest, emailBusy, onShowEmailTooltip, onHideTooltip, isMobileLayout, panelRef }) {
  if (!report) return <p className="assistant-text">No report selected.</p>;
  const [remainingOpen, setRemainingOpen] = useState(false);

  const topJobs = report.top_jobs || [];
  const remainingJobs = report.remaining_jobs || [];
  const title = report.report_title || report.report_name || report.report_path?.split("/").pop() || "Untitled";

  return (
    <section className="report-panel" ref={panelRef}>
      <div className="report-panel-header">
        <h3>
          <span className="report-label">Report:&nbsp;&nbsp;</span>
          <span className="report-title">{`${title}`}</span>
        </h3>
        <button
          disabled={emailBusy}
          onClick={onEmailLatest}
          onMouseEnter={isMobileLayout ? undefined : onShowEmailTooltip}
          onMouseLeave={isMobileLayout ? undefined : onHideTooltip}
          aria-label="Send report email"
          className=""
        >
          <FontAwesomeIcon icon={faEnvelope} />
        </button>
      </div>

      <section className="report-section">
        <h4>Top Jobs</h4>
        <div className="jobs-row">
          {topJobs.length > 0 ? topJobs.map((job) => (
            <JobCard key={job.job_id || job.url} job={job} isMobileLayout={isMobileLayout} />
          )) : <p className="assistant-text">No top jobs in this report.</p>}
        </div>
      </section>

      <section className="report-section">
        <button
          type="button"
          className={`remaining-toggle ${remainingOpen ? "open" : ""}`}
          onClick={() => setRemainingOpen((open) => !open)}
          aria-expanded={remainingOpen}
        >
          <h4>Remaining Jobs</h4>
          <FontAwesomeIcon icon={faChevronDown} className={`remaining-chevron ${remainingOpen ? "open" : ""}`} />
        </button>

        <div className={`remaining-content ${remainingOpen ? "open" : ""}`}>
          <div className="jobs-row">
            {remainingJobs.length > 0 ? remainingJobs.map((job) => (
              <JobCard key={job.job_id || job.url} job={job} isMobileLayout={isMobileLayout} />
            )) : <p className="assistant-text">No remaining jobs in this report.</p>}
          </div>
        </div>
      </section>
    </section>
  );
}

function ResumePresentIcon({ className = "" }) {
  return (
    <span className={`resume-file-with-badge ${className}`.trim()} aria-hidden="true">
      <FontAwesomeIcon icon={faFile} />
      <span className="resume-file-check-badge">
        <FontAwesomeIcon icon={faCheck} />
      </span>
    </span>
  );
}

function ResumePicker({
  uploads,
  open,
  closing,
  busy,
  activeResumeName,
  rowRef,
  pulsingResumeName,
  apiBase,
  onAddClick,
  onSelect,
  onDelete,
  onPlusMouseEnter,
  onItemMouseEnter,
  onItemMouseLeave,
  onAddMouseLeave,
}) {
  return (
    <div className={`resume-picker ${open ? "open" : ""}`}>
      {uploads.length > 0 && (open || closing) && (
        <button
          type="button"
          className="resume-plus"
          onClick={onAddClick}
          onMouseEnter={onPlusMouseEnter}
          onMouseLeave={onAddMouseLeave}
          disabled={busy}
          aria-label="Upload another resume"
        >
          <FontAwesomeIcon icon={faPlus} />
        </button>
      )}
      <div
        className="resume-picker-row"
        ref={rowRef}
        style={{ "--resume-strip-item-count": Math.max(1, uploads.length + (uploads.length > 0 ? 1 : 0)) }}
      >
        {uploads.map((item, index) => {
          const thumbSrc = item.thumbnail_url ? `${apiBase}${item.thumbnail_url}` : "";
          const isActive = item.is_active || item.name === activeResumeName;
          return (
            <div key={item.name} className="resume-item" data-resume-name={item.name}>
              <button
                type="button"
                className={`resume-chip ${isActive ? "active" : ""} ${pulsingResumeName === item.name ? "pulse" : ""}`}
                aria-label={item.display_name}
                onClick={() => onSelect(item.name)}
                style={thumbSrc ? { backgroundImage: `url(${thumbSrc})` } : undefined}
                onMouseEnter={(event) => onItemMouseEnter(event, item.display_name)}
                onMouseLeave={onItemMouseLeave}
              >
                {index + 1}
              </button>
              <button
                type="button"
                className="resume-chip-delete"
                aria-label={`Delete ${item.display_name}`}
                onClick={() => onDelete(item.name)}
              >
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(() => getSessionId());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isMobileLayout, setIsMobileLayout] = useState(() => typeof window !== "undefined" && window.innerWidth <= 860);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileSidebarClosing, setMobileSidebarClosing] = useState(false);
  const [collapsedHoverArmed, setCollapsedHoverArmed] = useState(false);
  const [collapsedHoverActive, setCollapsedHoverActive] = useState(false);
  const [sidebarAnimating, setSidebarAnimating] = useState(false);
  const [deletingReportPath, setDeletingReportPath] = useState("");
  const [reports, setReports] = useState([]);
  const [selectedReportPath, setSelectedReportPath] = useState("");
  const [openReportMenu, setOpenReportMenu] = useState("");
  const [sidebarSearchActive, setSidebarSearchActive] = useState(false);
  const [sidebarSearchQuery, setSidebarSearchQuery] = useState("");

  const [messages, setMessages] = useState([]);
  const [focusRequest, setFocusRequest] = useState(null);

  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [searchDisplay, setSearchDisplay] = useState({
    transitionKey: "idle",
    headline: "",
    subline: "",
    shimmer: false,
  });
  const [searchStatusVisible, setSearchStatusVisible] = useState(false);
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailTo, setEmailTo] = useState("");
  const [showEmailValidation, setShowEmailValidation] = useState(false);
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleLoadingMessage, setScheduleLoadingMessage] = useState("Loading schedule...");
  const [scheduleSaving, setScheduleSaving] = useState(false);
  const scheduleLoadingTimersRef = useRef([]);
  const [scheduleForm, setScheduleForm] = useState(DEFAULT_SCHEDULE);
  const [scheduleDailyEnabled, setScheduleDailyEnabled] = useState(false);
  const [showScheduleEmailValidation, setShowScheduleEmailValidation] = useState(false);
  const [scheduleToastVisible, setScheduleToastVisible] = useState(false);
  const [resumeToastVisible, setResumeToastVisible] = useState(false);
  const [resumeToastNonce, setResumeToastNonce] = useState(0);
  const [openResumeMessageId, setOpenResumeMessageId] = useState("");
  const [resumeThumbTooltip, setResumeThumbTooltip] = useState({ visible: false, text: "", top: 0, left: 0 });
  const [introMode, setIntroMode] = useState(true);
  const [introFadingOut, setIntroFadingOut] = useState(false);
  const [returningToIntro, setReturningToIntro] = useState(false);
  const [startupReveal, setStartupReveal] = useState(false);
  const [introSuggestion, setIntroSuggestion] = useState(() => getRandomIntroSuggestion());
  const [introSuggestionFadingOut, setIntroSuggestionFadingOut] = useState(false);
  const [hasResume, setHasResume] = useState(false);
  const [resumeUploads, setResumeUploads] = useState([]);
  const [resumePickerOpen, setResumePickerOpen] = useState(false);
  const [resumePlusClosing, setResumePlusClosing] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [floatingTooltip, setFloatingTooltip] = useState({ visible: false, text: "", top: 0, left: 0, placement: "left" });
  const [pulsingResumeName, setPulsingResumeName] = useState("");
  const activeResumeName = resumeUploads.find((item) => item.is_active)?.name || "";
  const resumePickerRowRef = useRef(null);
  const sidebarCollapsedForLayout = isMobileLayout ? false : sidebarCollapsed;

  function openMobileSidebar() {
    if (mobileSidebarCloseTimerRef.current) {
      clearTimeout(mobileSidebarCloseTimerRef.current);
      mobileSidebarCloseTimerRef.current = null;
    }
    setMobileSidebarClosing(false);
    setMobileSidebarOpen(true);
  }

  function closeMobileSidebar() {
    if (!mobileSidebarOpen || mobileSidebarClosing) return;
    setMobileSidebarClosing(true);
    if (mobileSidebarCloseTimerRef.current) {
      clearTimeout(mobileSidebarCloseTimerRef.current);
    }
    mobileSidebarCloseTimerRef.current = setTimeout(() => {
      setMobileSidebarOpen(false);
      setMobileSidebarClosing(false);
      mobileSidebarCloseTimerRef.current = null;
    }, 220);
  }

  const messageRefs = useRef({});
  const reportPanelRefs = useRef({});
  const chatContentRef = useRef(null);
  const chatLayoutRef = useRef(null);
  const fileInputRef = useRef(null);
  const introTextareaRef = useRef(null);
  const bottomTextareaRef = useRef(null);
  const composerOverlayRef = useRef(null);
  const sidebarAnimTimerRef = useRef(null);
  const sidebarSearchRef = useRef(null);
  const sidebarSearchInputRef = useRef(null);
  const resumePlusCloseTimerRef = useRef(null);
  const resumePulseTimerRef = useRef(null);
  const scheduleToastTimerRef = useRef(null);
  const resumeToastTimerRef = useRef(null);
  const chatAbortRef = useRef(null);
  const dragDepthRef = useRef(0);
  const dragClearTimerRef = useRef(null);
  const introSuggestionRotateTimerRef = useRef(null);
  const introSuggestionFadeTimerRef = useRef(null);
  const mobileSidebarCloseTimerRef = useRef(null);
  const searchSummaryHoldUntilRef = useRef(0);
  const searchRunIdRef = useRef("");
  const searchFetchFallbackRef = useRef("");
  const searchFetchJobKeyRef = useRef("");
  const searchFetchJobSinceRef = useRef(0);
  const bottomTextareaHeightRef = useRef(0);
  const touchPressedButtonRef = useRef(null);
  const searchStatusKey = searchDisplay.transitionKey || "idle";

  function clearTouchPressedButton() {
    touchPressedButtonRef.current?.classList.remove("touch-pressed");
    touchPressedButtonRef.current = null;
  }

  function getMobileReportScrollOffset() {
    if (!isMobileLayout) return 16;
    const header = document.querySelector(".mobile-header");
    const headerHeight = header?.getBoundingClientRect().height || 58;
    return headerHeight + 16;
  }

  function handleMobileButtonPointerDown(event) {
    if (!isMobileLayout || event.pointerType === "mouse") return;
    const button = event.target.closest?.(
      ".mobile-menu-button, .sidebar button, .resume-picker button, .composer-shell button",
    );
    if (!button || button.disabled) return;
    clearTouchPressedButton();
    button.classList.add("touch-pressed");
    touchPressedButtonRef.current = button;
  }

  function appendText(text, role = "assistant", focusBlock = null, extra = {}) {
    const newId = crypto.randomUUID();
    setMessages((previous) => [...previous, { id: newId, role, type: "text", text, ...extra }]);
    if (focusBlock) {
      setFocusRequest({ id: newId, block: focusBlock });
    }
  }

  function upsertReportMessage(report, replaceIfLastReport, focusBlock = "end") {
    const newId = crypto.randomUUID();
    setMessages((previous) => {
      const message = { id: newId, role: "assistant", type: "report", report };
      if (replaceIfLastReport && previous.length > 0 && previous[previous.length - 1].type === "report") {
        return [...previous.slice(0, -1), message];
      }
      return [...previous, message];
    });
    setFocusRequest({ id: newId, block: focusBlock });
  }

  async function refreshReports() {
    const listData = await api("/api/reports");
    setReports(listData.reports || []);
    return listData.reports || [];
  }

  async function refreshResumeUploads() {
    const payload = await api("/api/resume/uploads");
    const items = payload.resumes || [];
    setResumeUploads(items);
    setHasResume(items.length > 0);
    if (items.length === 0) {
      setResumePickerOpen(false);
    }
    return items;
  }

  useEffect(() => {
    (async () => {
      try {
        await Promise.all([
          refreshReports(),
          refreshResumeUploads(),
        ]);
      } catch (error) {
        appendText(error.message);
      }
    })();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    let frameId = 0;
    const scheduleUpdate = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(setViewportHeightVariable);
    };

    setViewportHeightVariable();
    window.addEventListener("resize", scheduleUpdate);
    window.addEventListener("orientationchange", scheduleUpdate);
    window.visualViewport?.addEventListener("resize", scheduleUpdate);
    window.visualViewport?.addEventListener("scroll", scheduleUpdate);

    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("resize", scheduleUpdate);
      window.removeEventListener("orientationchange", scheduleUpdate);
      window.visualViewport?.removeEventListener("resize", scheduleUpdate);
      window.visualViewport?.removeEventListener("scroll", scheduleUpdate);
    };
  }, []);

  useEffect(() => {
    if (!focusRequest?.id) return;
    const focusedMessage = messages.find((message) => message.id === focusRequest.id);
    const target = focusedMessage?.type === "report"
      ? reportPanelRefs.current[focusRequest.id]
      : messageRefs.current[focusRequest.id];
    if (target) {
      if (isMobileLayout && focusedMessage?.type === "report") {
        const container = chatLayoutRef.current;
        if (container) {
          const containerRect = container.getBoundingClientRect();
          const targetRect = target.getBoundingClientRect();
          const nextTop = container.scrollTop + (targetRect.top - containerRect.top) - getMobileReportScrollOffset();
          container.scrollTo({ top: Math.max(0, nextTop), behavior: "smooth" });
        }
      } else {
        target.scrollIntoView({ behavior: "smooth", block: focusRequest.block || "end" });
      }
    }
  }, [focusRequest, messages, isMobileLayout]);

  useEffect(() => {
    if (!isMobileLayout || !selectedReportPath) return;

    const targetMessage = messages.find((message) => message.type === "report" && message.report?.report_path === selectedReportPath);
    if (!targetMessage) return;

    const frameId = window.requestAnimationFrame(() => {
      const target = reportPanelRefs.current[targetMessage.id];
      const container = chatLayoutRef.current;
      if (!target || !container) return;
      const containerRect = container.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const nextTop = container.scrollTop + (targetRect.top - containerRect.top) - getMobileReportScrollOffset();
      container.scrollTo({ top: Math.max(0, nextTop), behavior: "smooth" });
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [isMobileLayout, messages, selectedReportPath]);

  useEffect(() => {
    function updateLastChatExtraPadding() {
      const container = chatContentRef.current;
      if (!container) return;
      const messagesInView = container.querySelectorAll(".chat-message");
      if (messagesInView.length === 0) {
        container.style.setProperty("--last-chat-extra-pad", "0px");
        return;
      }

      const last = messagesInView[messagesInView.length - 1];
      const lastBottom = last.offsetTop + last.offsetHeight;
      const remaining = container.clientHeight - lastBottom;
      const extra = Math.max(0, remaining);
      container.style.setProperty("--last-chat-extra-pad", `${extra}px`);
    }

    updateLastChatExtraPadding();
    window.addEventListener("resize", updateLastChatExtraPadding);
    return () => {
      window.removeEventListener("resize", updateLastChatExtraPadding);
    };
  }, [messages, introMode, resumePickerOpen]);

  useEffect(() => {
    if (!busy) {
      searchSummaryHoldUntilRef.current = 0;
      searchRunIdRef.current = "";
      searchFetchJobKeyRef.current = "";
      searchFetchJobSinceRef.current = 0;
      setSearchStatusVisible(false);
      setSearchDisplay({
        transitionKey: "idle",
        headline: "",
        subline: "",
        shimmer: false,
      });
      return undefined;
    }

    let cancelled = false;

    function buildDisplay(run) {
      const now = Date.now();
      const result = run?.result || {};
      const step = String(run?.step || "").toLowerCase();
      const runId = String(run?.run_id || "");
      const phase = String(result.phase || "").toLowerCase();
      const scrapedCount = Number(result.scraped_count || 0) || 0;
      const scoringIndex = Number(result.scoring_index || 0) || 0;
      const scoringTotal = Number(result.scoring_total || 0) || 0;
      const freshCount = Number(result.fresh_count || result.kept_count || 0) || 0;
      const currentTitle = String(result.current_job_title || "").trim();
      const currentCompany = String(result.current_job_company || "").trim();
      const currentJobKey = currentTitle || currentCompany ? `${currentTitle}||${currentCompany}` : "";
      const hasReportData = Boolean(
        result.report_path
        || result.report
        || (Array.isArray(result.top_jobs) && result.top_jobs.length > 0)
        || (Array.isArray(result.remaining_jobs) && result.remaining_jobs.length > 0)
      );

      if (runId && searchRunIdRef.current !== runId) {
        searchRunIdRef.current = runId;
        searchSummaryHoldUntilRef.current = 0;
        searchFetchFallbackRef.current = getRandomFetchingFallback();
        searchFetchJobKeyRef.current = "";
        searchFetchJobSinceRef.current = 0;
      }

      if (step.includes("fetch") || phase === "fetching") {
        const now = Date.now();
        if (currentJobKey) {
          if (searchFetchJobKeyRef.current !== currentJobKey) {
            searchFetchJobKeyRef.current = currentJobKey;
            searchFetchJobSinceRef.current = now;
          }
        } else {
          searchFetchJobKeyRef.current = "";
          searchFetchJobSinceRef.current = 0;
        }

        const jobAge = currentJobKey ? now - searchFetchJobSinceRef.current : 0;
        const showJobLabel = Boolean(currentJobKey) && jobAge <= 7000;

        return {
          transitionKey: "hunting",
          headline: "Hunting for Jobs...",
          subline: showJobLabel
            ? (currentCompany ? `Found ${currentTitle} at ${currentCompany}` : `Found ${currentTitle}`)
            : `${searchFetchFallbackRef.current || "Fetching"}...`,
          shimmer: true,
        };
      }

      if (step.includes("filter") || phase === "filtering") {
        return {
          transitionKey: "hunting",
          headline: "Hunting for Jobs...",
          subline: "Filtering...",
          shimmer: true,
        };
      }

      if (step.includes("score") || phase === "scoring") {
        if (!searchSummaryHoldUntilRef.current) {
          searchSummaryHoldUntilRef.current = now + 3000;
          return {
            transitionKey: "scoring-summary",
            headline: `${freshCount || scrapedCount} jobs found`,
            subline: "Preparing scoring...",
            shimmer: true,
          };
        }

        if (now < searchSummaryHoldUntilRef.current) {
          return {
            transitionKey: "scoring-summary",
            headline: `${freshCount || scrapedCount} jobs found`,
            subline: "Preparing scoring...",
            shimmer: true,
          };
        }

        return {
          transitionKey: "scoring",
          headline: scoringTotal ? `Scoring jobs (${scoringIndex}/${scoringTotal})` : "Scoring jobs",
          subline: currentTitle ? (currentCompany ? `${currentTitle} at ${currentCompany}` : currentTitle) : "",
          shimmer: true,
        };
      }

      if ((step.includes("build") || phase === "building" || run?.status === "complete") && hasReportData) {
        return {
          transitionKey: "building",
          headline: "Building Report",
          subline: "",
          shimmer: true,
        };
      }

      return {
        transitionKey: "idle",
        headline: "",
        subline: "",
        shimmer: false,
      };
    }

    let inFlight = false;
    const poll = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      try {
        const payload = await api(`/api/chat/status?session_id=${encodeURIComponent(sessionId)}`);
        if (cancelled) return;
        const run = payload?.run || null;
        if (!payload?.active || !run) {
          return;
        }
        const nextDisplay = buildDisplay(run);
        if (nextDisplay.headline || nextDisplay.subline) {
          setSearchStatusVisible(true);
          setSearchDisplay(nextDisplay);
        }
      } catch (error) {
        // Ignore polling errors while the request is in flight.
      } finally {
        inFlight = false;
      }
    };

    void poll();
    const timer = setInterval(() => {
      void poll();
    }, 300);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [busy]);

  useEffect(() => {
    const onDocClick = () => setOpenReportMenu("");
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  useEffect(() => {
    function handleOutsideClick(event) {
      if (!sidebarSearchActive) return;
      if (!sidebarSearchRef.current?.contains(event.target)) {
        setSidebarSearchActive(false);
        setSidebarSearchQuery("");
      }
    }

    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [sidebarSearchActive]);

  useEffect(() => {
    function handleResumePickerOutsideClick(event) {
      if (!resumePickerOpen) return;
      const target = event.target;
      const clickedTextarea = target instanceof Element && Boolean(
        target.closest(".bottom-composer-textarea")
      );
      if (clickedTextarea) return;
      const insideResumeUi = target instanceof Element && Boolean(
        target.closest(".resume-picker") ||
        target.closest(".resume-toggle-button") ||
        target.closest(".resume-icon-stack")
      );

      if (!insideResumeUi) {
        onResumeButtonClick();
        hideTooltip();
      }
    }

    document.addEventListener("mousedown", handleResumePickerOutsideClick);
    return () => document.removeEventListener("mousedown", handleResumePickerOutsideClick);
  }, [resumePickerOpen]);

  useEffect(() => {
    function handleResumePickerScroll() {
      if (!resumePickerOpen) return;
      onResumeButtonClick();
      hideTooltip();
    }

    window.addEventListener("scroll", handleResumePickerScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleResumePickerScroll);
  }, [resumePickerOpen]);

  useEffect(() => {
    if (!resumePickerOpen || !activeResumeName) return;
    const row = resumePickerRowRef.current;
    if (!row) return;

    const frame = window.requestAnimationFrame(() => {
      const activeItem = row.querySelector(`[data-resume-name="${CSS.escape(activeResumeName)}"]`);
      if (!activeItem) return;
      row.scrollTo({
        left: Math.max(0, activeItem.offsetLeft - 2),
        behavior: "smooth",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [resumePickerOpen, activeResumeName, resumeUploads.length]);

  useEffect(() => {
    function handleGlobalTypeToFocus(event) {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      ) {
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.length !== 1) return;

      event.preventDefault();
      const textarea = introMode ? introTextareaRef.current : bottomTextareaRef.current;
      if (!textarea) return;
      if (resumePickerOpen) {
        onResumeButtonClick();
      }
      textarea.focus();
      setQuery((previous) => `${previous}${event.key}`);
      requestAnimationFrame(() => {
        const end = textarea.value.length;
        textarea.setSelectionRange(end, end);
      });
    }

    document.addEventListener("keydown", handleGlobalTypeToFocus);
    return () => document.removeEventListener("keydown", handleGlobalTypeToFocus);
  }, [introMode, resumePickerOpen]);

  useEffect(() => {
    function handleGlobalPasteToFocus(event) {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      ) {
        return;
      }

      const pastedText = event.clipboardData?.getData("text/plain");
      if (!pastedText) return;

      event.preventDefault();
      const textarea = introMode ? introTextareaRef.current : bottomTextareaRef.current;
      if (!textarea) return;
      if (resumePickerOpen) {
        onResumeButtonClick();
      }
      textarea.focus();
      setQuery((previous) => `${previous}${pastedText}`);
    }

    document.addEventListener("paste", handleGlobalPasteToFocus);
    return () => document.removeEventListener("paste", handleGlobalPasteToFocus);
  }, [introMode, resumePickerOpen]);

  useEffect(() => {
    function clearDragOverlay() {
      dragDepthRef.current = 0;
      setDragActive(false);
      if (dragClearTimerRef.current) {
        clearTimeout(dragClearTimerRef.current);
        dragClearTimerRef.current = null;
      }
    }

    function scheduleDragOverlayClear() {
      if (dragClearTimerRef.current) {
        clearTimeout(dragClearTimerRef.current);
      }
      dragClearTimerRef.current = setTimeout(() => {
        clearDragOverlay();
      }, 120);
    }

    function isFileDrag(event) {
      const dataTransfer = event.dataTransfer;
      if (!dataTransfer) return false;
      if (dataTransfer.types && Array.from(dataTransfer.types).includes("Files")) {
        return true;
      }
      return Array.from(dataTransfer.items || []).some((item) => item.kind === "file");
    }

    function isPdfFile(file) {
      const name = String(file?.name || "").toLowerCase();
      return Boolean(
        file &&
        (file.type === "application/pdf" || name.endsWith(".pdf"))
      );
    }

    function setDragStateFromEvent(event) {
      if (!isFileDrag(event)) return false;
      event.preventDefault();
      dragDepthRef.current += 1;
      setDragActive(true);
      scheduleDragOverlayClear();
      return true;
    }

    function handleDragEnter(event) {
      setDragStateFromEvent(event);
    }

    function handleDragOver(event) {
      const isFile = setDragStateFromEvent(event);
      if (!isFile) return;
      event.dataTransfer.dropEffect = busy ? "none" : "copy";
      scheduleDragOverlayClear();
    }

    function handleDragLeave(event) {
      if (!isFileDrag(event)) return;
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) {
        clearDragOverlay();
      }
    }

    function handleDrop(event) {
      if (!isFileDrag(event)) return;
      event.preventDefault();
      clearDragOverlay();
      if (busy) return;

      const files = Array.from(event.dataTransfer?.files || []);
      const pdfFile = files.find(isPdfFile);
      if (pdfFile) {
        void handleUpload(pdfFile);
        return;
      }

      appendText("Please upload a PDF resume.");
    }

    function handleDragEnd() {
      clearDragOverlay();
    }

    window.addEventListener("dragenter", handleDragEnter);
    window.addEventListener("dragover", handleDragOver);
    window.addEventListener("dragleave", handleDragLeave);
    window.addEventListener("drop", handleDrop);
    window.addEventListener("dragend", handleDragEnd);
    return () => {
    window.removeEventListener("dragenter", handleDragEnter);
    window.removeEventListener("dragover", handleDragOver);
    window.removeEventListener("dragleave", handleDragLeave);
    window.removeEventListener("drop", handleDrop);
    window.removeEventListener("dragend", handleDragEnd);
    if (dragClearTimerRef.current) {
      clearTimeout(dragClearTimerRef.current);
    }
    };
  }, [busy]);

  useEffect(() => {
    return () => {
      if (sidebarAnimTimerRef.current) {
        clearTimeout(sidebarAnimTimerRef.current);
      }
      if (resumePlusCloseTimerRef.current) {
        clearTimeout(resumePlusCloseTimerRef.current);
      }
      if (resumePulseTimerRef.current) {
        clearTimeout(resumePulseTimerRef.current);
      }
      if (scheduleToastTimerRef.current) {
        clearTimeout(scheduleToastTimerRef.current);
      }
      if (resumeToastTimerRef.current) {
        clearTimeout(resumeToastTimerRef.current);
      }
      if (chatAbortRef.current) {
        chatAbortRef.current.abort();
      }
    };
  }, []);

  async function loadReport(reportPath) {
    try {
      if (isMobileLayout) {
        closeMobileSidebar();
      }
      if (introMode) {
        setIntroFadingOut(true);
        await new Promise((resolve) => setTimeout(resolve, 280));
        setIntroMode(false);
        setIntroFadingOut(false);
      }

      const item = await api(`/api/reports/item?report_path=${encodeURIComponent(reportPath)}`);
      setSelectedReportPath(reportPath);
      upsertReportMessage(item, true, "start");
      setOpenReportMenu("");
    } catch (error) {
      appendText(error.message);
    }
  }

  async function deleteReport(reportPath) {
    try {
      setDeletingReportPath(reportPath);

      await new Promise((resolve) => {
        setTimeout(resolve, 220);
      });

      await api(`/api/reports/item?report_path=${encodeURIComponent(reportPath)}`, { method: "DELETE" });
      setOpenReportMenu("");
      setDeletingReportPath("");

      const updated = await refreshReports();
      if (selectedReportPath === reportPath) {
        if (updated.length > 0) {
          await loadReport(updated[0].report_path);
        } else {
          setSelectedReportPath("");
          appendText("Report deleted.");
        }
      }
    } catch (error) {
      setDeletingReportPath("");
      appendText(error.message);
    }
  }

  async function handleUpload(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      appendText("Please upload a PDF resume.");
      return;
    }

    setBusy(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_BASE}/api/resume/upload`, {
        method: "POST",
        body: formData,
      });

      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Upload failed");
      setHasResume(true);
      await refreshResumeUploads();
      setResumePickerOpen(true);
      setResumePlusClosing(false);
      setResumeToastNonce((value) => value + 1);
      setResumeToastVisible(true);
      if (resumeToastTimerRef.current) {
        clearTimeout(resumeToastTimerRef.current);
      }
      resumeToastTimerRef.current = setTimeout(() => {
        setResumeToastVisible(false);
      }, 4500);
    } catch (error) {
      appendText(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSearch() {
    const trimmed = query.trim();
    if (!trimmed || busy) return;

    if (introMode) {
      setIntroFadingOut(true);
      setTimeout(() => {
        setIntroMode(false);
        setIntroFadingOut(false);
      }, 280);
    }

    appendText(
      trimmed,
      "user",
      "start",
      {},
    );
    setQuery("");
    requestAnimationFrame(() => {
      resizeBottomComposerTextarea();
    });
    searchSummaryHoldUntilRef.current = 0;
    searchRunIdRef.current = "";
    setSearchStatusVisible(false);
    setSearchDisplay({
      transitionKey: "idle",
      headline: "",
      subline: "",
      shimmer: false,
    });
    setBusy(true);

    try {
      const abortController = new AbortController();
      chatAbortRef.current = abortController;
      const activeResume = resumeUploads.find((item) => item.is_active) || null;
      const payload = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          message: trimmed,
          session_id: sessionId,
          resume_name: activeResume?.name || "",
          resume_display_name: activeResume?.display_name || "",
          timezone: getBrowserTimeZone(),
        }),
        signal: abortController.signal,
      });
      chatAbortRef.current = null;
      if (payload.report) {
        upsertReportMessage(payload.report, true, "start");
        if (payload.report.report_path) {
          setSelectedReportPath(payload.report.report_path);
          await refreshReports();
        }
        if (payload.assistant_message && String(payload.assistant_message).trim()) {
          setBusy(false);
          return;
        }
      }
      appendText(payload.assistant_message || "Done.", "assistant", "start");
      setBusy(false);
    } catch (error) {
      chatAbortRef.current = null;
      setBusy(false);
      if (error?.name === "AbortError") {
        appendText("Stopped.");
        return;
      }
      const errorMessage = String(error?.message || "");
      const isConnectionFailure = /load failed|failed to fetch|networkerror|network request failed/i.test(errorMessage);
      appendText(
        isConnectionFailure
          ? "The search connection ended before it could finish. Please try again with a narrower search."
          : errorMessage || "The search could not be completed.",
      );
    }
  }

  async function handleStop() {
    try {
      await api(`/api/chat/stop?session_id=${encodeURIComponent(sessionId)}`, {
        method: "POST",
      });
    } catch (error) {
      // Ignore stop errors; aborting the client request still matters.
    } finally {
      if (chatAbortRef.current) {
        chatAbortRef.current.abort();
      }
      setBusy(false);
    }
  }

  function openEmailModal() {
    setEmailModalOpen(true);
    setShowEmailValidation(false);
  }

  function normalizeSchedulePayload(payload) {
    return convertScheduleForViewer(
      payload,
      String(payload?.timezone || DEFAULT_SCHEDULE.timezone || getBrowserTimeZone()),
      getBrowserTimeZone(),
    );
  }

  async function openScheduleModal() {
    setScheduleModalOpen(true);
    setShowScheduleEmailValidation(false);
    setScheduleLoading(true);
    setScheduleLoadingMessage("Loading schedule...");
    scheduleLoadingTimersRef.current.forEach((timerId) => clearTimeout(timerId));
    scheduleLoadingTimersRef.current = [];
    scheduleLoadingTimersRef.current.push(
      setTimeout(() => {
        setScheduleLoadingMessage("Just a sec...");
      }, 6000),
    );
    scheduleLoadingTimersRef.current.push(
      setTimeout(() => {
        setScheduleLoadingMessage("Almost got it...");
      }, 11000),
    );
    try {
      const payload = await api("/api/schedule");
      const normalized = normalizeSchedulePayload(payload);
      setScheduleForm(normalized);
      setScheduleDailyEnabled(Object.values(normalized.days).every(Boolean));
    } catch (error) {
      appendText(error.message);
      setScheduleForm(DEFAULT_SCHEDULE);
      setScheduleDailyEnabled(Object.values(DEFAULT_SCHEDULE.days).every(Boolean));
    } finally {
      setScheduleLoading(false);
      scheduleLoadingTimersRef.current.forEach((timerId) => clearTimeout(timerId));
      scheduleLoadingTimersRef.current = [];
      setScheduleLoadingMessage("Loading schedule...");
    }
  }

  function handleCancelScheduleModal() {
    setScheduleModalOpen(false);
    setShowScheduleEmailValidation(false);
    setScheduleLoading(false);
    scheduleLoadingTimersRef.current.forEach((timerId) => clearTimeout(timerId));
    scheduleLoadingTimersRef.current = [];
    setScheduleLoadingMessage("Loading schedule...");
  }

  useEffect(() => () => {
    scheduleLoadingTimersRef.current.forEach((timerId) => clearTimeout(timerId));
  }, []);

  function toggleScheduleDay(dayKey) {
    setScheduleForm((previous) => {
      const nextDays = {
        ...previous.days,
        [dayKey]: !previous.days[dayKey],
      };
      setScheduleDailyEnabled(Object.values(nextDays).every(Boolean));
      return {
        ...previous,
        days: nextDays,
      };
    });
  }

  function toggleDailyDays() {
    setScheduleDailyEnabled((previous) => {
      const next = !previous;
      setScheduleForm((current) => ({
        ...current,
        days: {
          mon: next,
          tue: next,
          wed: next,
          thu: next,
          fri: next,
          sat: next,
          sun: next,
        },
      }));
      return next;
    });
  }

  async function handleSaveSchedule() {
    const hasDayEnabled = Object.values(scheduleForm.days).some(Boolean);
    if (!hasDayEnabled && scheduleForm.enabled) {
      appendText("Enable at least one day for the scheduler.");
      return;
    }
    if (scheduleForm.enabled && !String(scheduleForm.keywords || "").trim()) {
      appendText("Enter a search query for the scheduler.");
      return;
    }
    const trimmedScheduleEmail = scheduleForm.email_to.trim();
    if (trimmedScheduleEmail && !EMAIL_REGEX.test(trimmedScheduleEmail)) {
      setShowScheduleEmailValidation(true);
      return;
    }
    const parsedPages = Number(String(scheduleForm.pages || "").trim());
    const normalizedPages = Number.isFinite(parsedPages)
      ? Math.min(4, Math.max(1, Math.trunc(parsedPages)))
      : 1;

    setShowScheduleEmailValidation(false);
    setScheduleSaving(true);
    try {
      const payload = await api("/api/schedule", {
        method: "POST",
        body: JSON.stringify({
          ...scheduleForm,
          pages: normalizedPages,
          timezone: getBrowserTimeZone(),
          email_to: trimmedScheduleEmail,
        }),
      });
      const normalized = normalizeSchedulePayload(payload);
      setScheduleForm(normalized);
      setScheduleDailyEnabled(Object.values(normalized.days).every(Boolean));
      setScheduleModalOpen(false);
      setScheduleToastVisible(true);
      if (scheduleToastTimerRef.current) {
        clearTimeout(scheduleToastTimerRef.current);
      }
      scheduleToastTimerRef.current = setTimeout(() => {
        setScheduleToastVisible(false);
      }, 3000);
    } catch (error) {
      appendText(error.message);
    } finally {
      setScheduleSaving(false);
    }
  }

  function handleScheduleEnabledToggle() {
    setScheduleForm((previous) => {
      const nextEnabled = !previous.enabled;
      const trimmedEmail = previous.email_to.trim();
      const invalidEmail = trimmedEmail && !EMAIL_REGEX.test(trimmedEmail);
      return {
        ...previous,
        enabled: nextEnabled,
        email_to: !nextEnabled && invalidEmail ? "" : previous.email_to,
      };
    });
    setShowScheduleEmailValidation(false);
  }

  async function handleSendEmailFromModal() {
    const trimmedEmail = emailTo.trim();
    if (!EMAIL_REGEX.test(trimmedEmail)) {
      setShowEmailValidation(true);
      return;
    }
    setEmailBusy(true);
    try {
      const result = await api("/api/reports/latest/email", {
        method: "POST",
        body: JSON.stringify({ to_email: trimmedEmail }),
      });
      const statusText = result.email_result?.status === "sent"
        ? `Email sent to ${result.email_result.to}`
        : (result.email_result?.error || result.message || "Email failed");
      appendText(statusText, "assistant", "start");
      setEmailModalOpen(false);
      setShowEmailValidation(false);
    } catch (error) {
      appendText(error.message);
    } finally {
      setEmailBusy(false);
    }
  }

  function handleCancelEmailModal() {
    setEmailModalOpen(false);
    setShowEmailValidation(false);
  }

  async function handleDeleteUploadedResume(uploadName) {
    const deletingLast = resumeUploads.length <= 1;
    setResumeUploads((previous) => previous.filter((item) => item.name !== uploadName));
    if (deletingLast) {
      setHasResume(false);
      setResumePickerOpen(false);
      setResumePlusClosing(false);
      hideTooltip();
    }
    try {
      await api(`/api/resume/uploads/${encodeURIComponent(uploadName)}`, { method: "DELETE" });
      await refreshResumeUploads();
    } catch (error) {
      await refreshResumeUploads();
      appendText(error.message);
    }
  }

  async function handleSelectUploadedResume(uploadName) {
    try {
      setPulsingResumeName(uploadName);
      if (resumePulseTimerRef.current) {
        clearTimeout(resumePulseTimerRef.current);
      }
      resumePulseTimerRef.current = setTimeout(() => {
        setPulsingResumeName("");
      }, 180);
      await api(`/api/resume/uploads/${encodeURIComponent(uploadName)}/select`, { method: "POST" });
      await refreshResumeUploads();
    } catch (error) {
      appendText(error.message);
    }
  }

  function openResumePicker() {
    fileInputRef.current?.click();
  }

  function handleResumeInputChange(event) {
    const selectedFile = event.target.files?.[0] || null;
    handleUpload(selectedFile);
    event.target.value = "";
  }

  function handleAddResumeClick() {
    openResumePicker();
  }

  function onResumeButtonClick() {
    if (!hasResume) {
      openResumePicker();
      return;
    }
    setResumePickerOpen((open) => {
      if (open) {
        hideTooltip();
        setResumePlusClosing(true);
        if (resumePlusCloseTimerRef.current) {
          clearTimeout(resumePlusCloseTimerRef.current);
        }
        resumePlusCloseTimerRef.current = setTimeout(() => {
          setResumePlusClosing(false);
        }, 750);
        return false;
      }

      if (resumePlusCloseTimerRef.current) {
        clearTimeout(resumePlusCloseTimerRef.current);
      }
      setResumePlusClosing(false);
      return true;
    });
  }

  function showLeftTooltip(event, text) {
    if (isMobileLayout) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setFloatingTooltip({
      visible: true,
      text,
      top: rect.top + rect.height / 2,
      left: rect.left - 12,
      placement: "left",
    });
  }

  function showTopTooltip(event, text) {
    if (isMobileLayout) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const estimatedWidth = Math.min(260, Math.max(120, String(text || "").length * 7.5 + 24));
    const estimatedHeight = 32;
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const safeLeft = Math.min(
      Math.max(rect.left + rect.width / 2, estimatedWidth / 2 + 8),
      Math.max(estimatedWidth / 2 + 8, viewportWidth - estimatedWidth / 2 - 8),
    );
    const safeTop = Math.max(estimatedHeight + 8, rect.top - 8);
    setFloatingTooltip({
      visible: true,
      text,
      top: Math.min(safeTop, Math.max(estimatedHeight + 8, viewportHeight - 8)),
      left: safeLeft,
      placement: "top",
    });
  }

  function showRightTooltip(event, text) {
    if (isMobileLayout) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setFloatingTooltip({
      visible: true,
      text,
      top: rect.top + rect.height / 2,
      left: rect.right + 10,
      placement: "right",
    });
  }

  function showBottomTooltip(event, text) {
    if (isMobileLayout) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setFloatingTooltip({
      visible: true,
      text,
      top: rect.bottom + 10,
      left: rect.left + rect.width / 2,
      placement: "bottom",
    });
  }

  function showSidebarTooltip(event, text) {
    if (isMobileLayout) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setFloatingTooltip({
      visible: true,
      text,
      top: rect.top + rect.height / 2,
      left: rect.right + 10,
      placement: "right",
    });
  }

  function hideTooltip() {
    setFloatingTooltip({ visible: false, text: "", top: 0, left: 0, placement: "left" });
  }

  function getResumeToggleTooltipText() {
    if (!hasResume) return "Upload Resume";
    return "View Resumes";
  }

  useEffect(() => {
    if (isMobileLayout) {
      hideTooltip();
    }
  }, [isMobileLayout]);

  function showResumeThumbTooltip(event, text) {
    const rect = event.currentTarget.getBoundingClientRect();
    setResumeThumbTooltip({
      visible: true,
      text,
      top: rect.bottom + 8,
      left: rect.left + rect.width / 2,
    });
  }

  function hideResumeThumbTooltip() {
    setResumeThumbTooltip({ visible: false, text: "", top: 0, left: 0 });
  }

  async function handleNewHunt() {
    if (isMobileLayout) {
      closeMobileSidebar();
    }
    const sessionToReset = sessionId;

    if (chatAbortRef.current) {
      chatAbortRef.current.abort();
      chatAbortRef.current = null;
    }

    const stopUrl = `/api/chat/stop?session_id=${encodeURIComponent(sessionToReset)}`;
    const resetUrl = `/api/chat/reset?session_id=${encodeURIComponent(sessionToReset)}`;

    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon(stopUrl, "");
      navigator.sendBeacon(resetUrl, "");
    } else {
      void fetch(stopUrl, { method: "POST", keepalive: true }).catch(() => {});
      void fetch(resetUrl, { method: "POST", keepalive: true }).catch(() => {});
    }

    try {
      window.sessionStorage.removeItem("job_hunting_agent_session_id");
    } catch {
      // Ignore storage failures.
    }

    window.location.reload();
  }

  function handleSidebarSearchClick() {
    if (sidebarCollapsed) {
      setSidebarCollapsed(false);
    }
    setSidebarSearchActive(true);
    setTimeout(() => {
      sidebarSearchInputRef.current?.focus();
      sidebarSearchInputRef.current?.select();
    }, 40);
  }

  const filteredReports = reports.filter((item) => {
    const q = sidebarSearchQuery.trim().toLowerCase();
    if (!q) return true;
    const haystack = `${item.name || ""} ${item.report_path || ""}`.toLowerCase();
    return haystack.includes(q);
  });

  function handleSubmit(event) {
    event.preventDefault();
    if (busy) {
      void handleStop();
    } else {
      handleSearch();
    }
  }

  function onComposerKeyDown(event) {
    if (introMode && event.key === "Enter" && !event.shiftKey && !query.trim()) {
      event.preventDefault();
      setQuery(introSuggestion);
      return;
    }

    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
      return;
    }

    if (introMode && event.key === "Tab" && !event.shiftKey) {
      event.preventDefault();
      if (!query.trim()) {
        setQuery(introSuggestion);
      }
    }
  }

  function animateBottomTextareaToContent(textarea) {
    if (!textarea) return;
    const current = textarea.getBoundingClientRect().height;
    textarea.style.height = "auto";
    const content = textarea.value.length > 0 ? textarea.value : String(textarea.placeholder || "");
    const natural = content ? measureTextareaHeight(textarea, content) : textarea.scrollHeight;
    const maxHeight = 220;
    const target = Math.min(natural, maxHeight);
    textarea.classList.toggle("at-max-height", natural > maxHeight + 1);
    if (bottomTextareaHeightRef.current === 0) {
      textarea.style.height = `${target}px`;
      bottomTextareaHeightRef.current = target;
      return;
    }
    if (Math.abs(current - target) < 1) {
      textarea.style.height = `${target}px`;
      bottomTextareaHeightRef.current = target;
      return;
    }
    textarea.style.height = `${current}px`;
    void textarea.offsetHeight;
    textarea.style.height = `${target}px`;
    bottomTextareaHeightRef.current = target;
  }

  function measureTextareaHeight(textarea, text) {
    const clone = document.createElement("textarea");
    const computedStyle = window.getComputedStyle(textarea);
    const width = textarea.getBoundingClientRect().width || Number.parseFloat(computedStyle.width) || 0;
    const sizingProps = [
      "boxSizing",
      "width",
      "paddingTop",
      "paddingRight",
      "paddingBottom",
      "paddingLeft",
      "borderTopWidth",
      "borderRightWidth",
      "borderBottomWidth",
      "borderLeftWidth",
      "fontFamily",
      "fontSize",
      "fontWeight",
      "fontStyle",
      "lineHeight",
      "letterSpacing",
      "textTransform",
      "textIndent",
      "wordSpacing",
      "tabSize",
      "whiteSpace",
      "overflowWrap",
      "wordBreak",
    ];

    clone.style.position = "absolute";
    clone.style.visibility = "hidden";
    clone.style.top = "-9999px";
    clone.style.left = "-9999px";
    clone.style.height = "auto";
    clone.style.overflow = "hidden";
    clone.rows = 1;
    clone.value = text;
    if (width > 0) {
      clone.style.width = `${width}px`;
    }
    sizingProps.forEach((property) => {
      clone.style[property] = computedStyle[property];
    });

    document.body.appendChild(clone);
    const height = clone.scrollHeight;
    clone.remove();
    return height;
  }

  function resizeBottomComposerTextarea() {
    const textarea = bottomTextareaRef.current;
    animateBottomTextareaToContent(textarea);
  }

  function resizeIntroComposerTextarea() {
    const textarea = introTextareaRef.current;
    animateBottomTextareaToContent(textarea);
  }

  function handleBottomTextareaChange(event) {
    if (resumePickerOpen) {
      onResumeButtonClick();
    }
    setQuery(event.target.value);
    animateBottomTextareaToContent(event.target);
  }

  function handleIntroTextareaChange(event) {
    if (resumePickerOpen) {
      onResumeButtonClick();
    }
    setQuery(event.target.value);
    animateBottomTextareaToContent(event.target);
  }

  useEffect(() => {
    resizeBottomComposerTextarea();
    resizeIntroComposerTextarea();
  }, [introMode, resumePickerOpen]);

  useEffect(() => {
    resizeBottomComposerTextarea();
    resizeIntroComposerTextarea();
  }, [query]);

  useEffect(() => {
    resizeBottomComposerTextarea();
    resizeIntroComposerTextarea();
  }, [introSuggestion]);

  useEffect(() => {
    if (!introMode) return;
    setIntroSuggestion(() => getRandomIntroSuggestion());
    setIntroSuggestionFadingOut(false);
  }, [introMode]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setStartupReveal(true);
    }, 90);

    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!introMode || query.trim()) {
      if (introSuggestionRotateTimerRef.current) {
        clearTimeout(introSuggestionRotateTimerRef.current);
        introSuggestionRotateTimerRef.current = null;
      }
      if (introSuggestionFadeTimerRef.current) {
        clearTimeout(introSuggestionFadeTimerRef.current);
        introSuggestionFadeTimerRef.current = null;
      }
      setIntroSuggestionFadingOut(false);
      return undefined;
    }

    let cancelled = false;

    function scheduleNextRotation() {
      if (cancelled) return;
      if (introSuggestionRotateTimerRef.current) {
        clearTimeout(introSuggestionRotateTimerRef.current);
      }
      introSuggestionRotateTimerRef.current = window.setTimeout(() => {
        if (cancelled || query.trim()) return;
        setIntroSuggestionFadingOut(true);
        if (introSuggestionFadeTimerRef.current) {
          clearTimeout(introSuggestionFadeTimerRef.current);
        }

        introSuggestionFadeTimerRef.current = window.setTimeout(() => {
          if (cancelled || query.trim()) return;
          setIntroSuggestion((previousSuggestion) => getRandomIntroSuggestion(previousSuggestion));
          setIntroSuggestionFadingOut(false);
          scheduleNextRotation();
        }, INTRO_SUGGESTION_FADE_MS);
      }, INTRO_SUGGESTION_ROTATE_MS);
    }

    scheduleNextRotation();

    return () => {
      cancelled = true;
      if (introSuggestionRotateTimerRef.current) {
        clearTimeout(introSuggestionRotateTimerRef.current);
        introSuggestionRotateTimerRef.current = null;
      }
      if (introSuggestionFadeTimerRef.current) {
        clearTimeout(introSuggestionFadeTimerRef.current);
        introSuggestionFadeTimerRef.current = null;
      }
      setIntroSuggestionFadingOut(false);
    };
  }, [introMode, query]);

  useEffect(() => {
    function handleWindowResize() {
      resizeBottomComposerTextarea();
      resizeIntroComposerTextarea();
      const nextIsMobile = window.innerWidth <= 860;
      setIsMobileLayout(nextIsMobile);
      if (!nextIsMobile) {
        setMobileSidebarOpen(false);
        setMobileSidebarClosing(false);
        if (mobileSidebarCloseTimerRef.current) {
          clearTimeout(mobileSidebarCloseTimerRef.current);
          mobileSidebarCloseTimerRef.current = null;
        }
      }
    }
    window.addEventListener("resize", handleWindowResize);
    handleWindowResize();
    return () => window.removeEventListener("resize", handleWindowResize);
  }, []);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const shouldLockScroll = introMode || (isMobileLayout && (mobileSidebarOpen || mobileSidebarClosing));
    document.body.style.overflow = shouldLockScroll ? "hidden" : "";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [introMode, isMobileLayout, mobileSidebarOpen, mobileSidebarClosing]);

  useEffect(() => {
    if (!isMobileLayout) {
      clearTouchPressedButton();
      return undefined;
    }

    const clearPressedButton = () => clearTouchPressedButton();
    window.addEventListener("pointerup", clearPressedButton);
    window.addEventListener("pointercancel", clearPressedButton);
    window.addEventListener("blur", clearPressedButton);
    document.addEventListener("visibilitychange", clearPressedButton);

    return () => {
      clearTouchPressedButton();
      window.removeEventListener("pointerup", clearPressedButton);
      window.removeEventListener("pointercancel", clearPressedButton);
      window.removeEventListener("blur", clearPressedButton);
      document.removeEventListener("visibilitychange", clearPressedButton);
    };
  }, [isMobileLayout]);

  const trimmedEmail = emailTo.trim();
  const canSubmitQuery = query.trim().length > 0;
  const isEmailValid = EMAIL_REGEX.test(trimmedEmail);
  const showEmailError = showEmailValidation && !isEmailValid;
  const scheduleLocked = !scheduleForm.enabled;

  return (
    <>
    <main
      className={`app-shell ${sidebarCollapsedForLayout ? "sidebar-collapsed" : "sidebar-open"} ${resumePickerOpen ? "resume-picker-open" : ""} ${isMobileLayout ? "mobile-layout" : ""} ${isMobileLayout ? "tooltips-disabled" : sidebarAnimating ? "tooltips-disabled" : ""}`}
      onPointerDown={handleMobileButtonPointerDown}
      onPointerUp={clearTouchPressedButton}
      onPointerCancel={clearTouchPressedButton}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="visually-hidden-file-input"
        onChange={handleResumeInputChange}
      />
      {isMobileLayout && (
        <header className="mobile-header">
          <button
            type="button"
            className="mobile-menu-button"
            aria-label="Open sidebar"
            onClick={openMobileSidebar}
          >
            <HiMenuAlt1 />
          </button>
          <h1 className={`mobile-header-title ${startupReveal ? "app-title-fade-in" : "app-title-startup"}`}>Job-Hunting Agent</h1>
        </header>
      )}

      {isMobileLayout && mobileSidebarOpen && !mobileSidebarClosing && (
        <div className="mobile-sidebar-backdrop" onClick={closeMobileSidebar} aria-hidden="true" />
      )}

      <aside className={`sidebar ${!isMobileLayout && sidebarCollapsed ? "collapsed" : ""} ${isMobileLayout ? "mobile" : ""} ${isMobileLayout && mobileSidebarOpen ? "mobile-open" : ""} ${isMobileLayout && mobileSidebarClosing ? "mobile-closing" : ""}`}>
        <div className="sidebar-top">
          <div className="brand-box" aria-hidden={sidebarCollapsedForLayout || isMobileLayout}>
              <h2 className={`${startupReveal ? "app-title-fade-in" : "app-title-startup"}`}>Job-Hunting Agent</h2>
            </div>

          {isMobileLayout ? (
            <div className="sidebar-mobile-header">
              <button type="button" className="sidebar-mobile-target-button" aria-label="Target">
                <FontAwesomeIcon icon={faCrosshairs} className="sidebar-mobile-target-icon" />
              </button>
              <button
                type="button"
                className="icon-button sidebar-mobile-close"
                aria-label="Close sidebar"
                onClick={closeMobileSidebar}
              >
                <FontAwesomeIcon icon={faXmark} />
              </button>
            </div>
          ) : (
            <button
              className="icon-button sidebar-toggle"
              aria-label={sidebarCollapsedForLayout ? "Open sidebar" : "Collapse sidebar"}
              onMouseEnter={(event) => {
                showSidebarTooltip(event, sidebarCollapsedForLayout ? "Open sidebar" : "Collapse sidebar");
                if (sidebarCollapsedForLayout && collapsedHoverArmed) {
                  setCollapsedHoverActive(true);
                }
              }}
              onFocus={(event) => showSidebarTooltip(event, sidebarCollapsedForLayout ? "Open sidebar" : "Collapse sidebar")}
              onMouseLeave={() => {
                hideTooltip();
                if (sidebarCollapsedForLayout) {
                  setCollapsedHoverActive(false);
                  setCollapsedHoverArmed(true);
                }
              }}
              onBlur={hideTooltip}
              onClick={() => {
                setSidebarAnimating(true);
                if (sidebarAnimTimerRef.current) {
                  clearTimeout(sidebarAnimTimerRef.current);
                }
                sidebarAnimTimerRef.current = setTimeout(() => {
                  setSidebarAnimating(false);
                }, 230);

                setSidebarCollapsed((value) => {
                  const next = !value;
                  setCollapsedHoverArmed(false);
                  setCollapsedHoverActive(false);
                  return next;
                });
              }}
            >
              {!sidebarCollapsedForLayout && <FontAwesomeIcon icon={faRightToBracket} rotation={180} />}
              {sidebarCollapsedForLayout && (
                <span className={`collapsed-toggle-icons ${collapsedHoverActive ? "hover-active" : ""}`}>
                  <FontAwesomeIcon icon={faCrosshairs} className="bullseye-icon" />
                  <FontAwesomeIcon icon={faRightToBracket} className="open-icon" />
                </span>
              )}
            </button>
          )}
        </div>

        <div className="sidebar-actions">
          <button
            className="profile-button sidebar-action-button"
            onClick={() => { void handleNewHunt(); }}
            onMouseEnter={(event) => showSidebarTooltip(event, "New Hunt")}
            onFocus={(event) => showSidebarTooltip(event, "New Hunt")}
            onMouseLeave={hideTooltip}
            onBlur={hideTooltip}
          >
            <FontAwesomeIcon icon={faPenToSquare} className="sidebar-action-icon" />
            <span className={`profile-text sidebar-action-text ${sidebarCollapsedForLayout ? "hidden" : ""}`}>New Hunt</span>
          </button>
          <button
            className="profile-button sidebar-action-button"
            onClick={openScheduleModal}
            onMouseEnter={(event) => showSidebarTooltip(event, "Schedule")}
            onFocus={(event) => showSidebarTooltip(event, "Schedule")}
            onMouseLeave={hideTooltip}
            onBlur={hideTooltip}
          >
            <FontAwesomeIcon icon={faCalendarDays} className="sidebar-action-icon" />
            <span className={`profile-text sidebar-action-text ${sidebarCollapsedForLayout ? "hidden" : ""}`}>Schedule</span>
          </button>
          <div ref={sidebarSearchRef} className="sidebar-search-wrap">
            <button
              className="profile-button sidebar-action-button"
              onClick={handleSidebarSearchClick}
              onMouseEnter={(event) => showSidebarTooltip(event, "Search")}
              onFocus={(event) => showSidebarTooltip(event, "Search")}
              onMouseLeave={hideTooltip}
              onBlur={hideTooltip}
            >
              <FontAwesomeIcon icon={faMagnifyingGlass} className="sidebar-action-icon" />
              {!sidebarSearchActive && (
                <span className={`profile-text sidebar-action-text ${sidebarCollapsedForLayout ? "hidden" : ""}`}>Search</span>
              )}
              {sidebarSearchActive && !sidebarCollapsedForLayout && (
                <input
                  ref={sidebarSearchInputRef}
                  className="sidebar-search-input"
                  value={sidebarSearchQuery}
                  onChange={(event) => setSidebarSearchQuery(event.target.value)}
                  onClick={(event) => event.stopPropagation()}
                  placeholder="Search reports..."
                />
              )}
            </button>
          </div>
        </div>

        {!sidebarCollapsedForLayout && <h3 className="report-list-title">Reports</h3>}
        <div className="report-list">
          {filteredReports.length === 0 && !sidebarCollapsedForLayout && <p className="muted">No reports found.</p>}

          {filteredReports.map((item) => (
            <div
              key={item.report_path}
              className={`report-item-wrap ${deletingReportPath === item.report_path ? "deleting" : ""}`}
              onClick={(event) => event.stopPropagation()}
            >
              <button
                className={`report-item ${selectedReportPath === item.report_path ? "active" : ""}`}
                onClick={() => loadReport(item.report_path)}
                title={item.name}
              >
                {sidebarCollapsedForLayout ? "•" : item.name}
              </button>

              {!isMobileLayout && !sidebarCollapsedForLayout && (
                <>
                  <button
                    className={`report-menu-trigger ${openReportMenu === item.report_path ? "active" : ""}`}
                    title="Report options"
                    onClick={(event) => {
                      event.stopPropagation();
                      setOpenReportMenu((current) => current === item.report_path ? "" : item.report_path);
                    }}
                  >
                    <FontAwesomeIcon icon={faEllipsis} />
                  </button>

                  {openReportMenu === item.report_path && (
                    <div className="report-menu">
                      <button onClick={() => deleteReport(item.report_path)}>Delete report</button>
                    </div>
                  )}
                </>
              )}
              {isMobileLayout && !sidebarCollapsedForLayout && (
                <>
                  <button
                    className={`report-menu-trigger mobile-visible ${openReportMenu === item.report_path ? "active" : ""}`}
                    title="Report options"
                    onClick={(event) => {
                      event.stopPropagation();
                      setOpenReportMenu((current) => current === item.report_path ? "" : item.report_path);
                    }}
                  >
                    <FontAwesomeIcon icon={faEllipsis} />
                  </button>

                  {openReportMenu === item.report_path && (
                    <div className="report-menu">
                      <button onClick={() => deleteReport(item.report_path)}>Delete report</button>
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>

        <div className="sidebar-bottom">
          <button
            className="profile-button"
            type="button"
            aria-label="About"
          >
            <FontAwesomeIcon icon={faCircleQuestion} className="profile-icon profile-icon-about" />
            <span className={`profile-text profile-text-about ${sidebarCollapsedForLayout ? "hidden" : ""}`}>About</span>
          </button>
        </div>
      </aside>

      <section ref={chatLayoutRef} className={`chat-layout ${introMode ? "intro-scroll-locked" : ""}`} onClick={() => setOpenReportMenu("")}>
        {scheduleToastVisible && (
          <div className="schedule-save-toast" role="status" aria-live="polite">
            <span>Schedule saved</span>
            <span className="schedule-save-toast-icon">
              <FontAwesomeIcon icon={faCheck} />
            </span>
          </div>
        )}
        {resumeToastVisible && (
          <div key={resumeToastNonce} className="resume-upload-toast" role="status" aria-live="polite">
            <span>Resume uploaded</span>
            <span className="schedule-save-toast-icon">
              <FontAwesomeIcon icon={faCheck} />
            </span>
          </div>
        )}
        <div className={`chat-column ${introMode ? "intro-mode" : "docked-mode"}`}>
        {dragActive && createPortal(
          <div className="resume-drop-overlay" aria-hidden="true">
            <div className="resume-drop-overlay-card">
              <FontAwesomeIcon icon={faFileArrowUp} className="resume-drop-overlay-icon" />
              <p>Drop your resume anywhere (.pdf)</p>
            </div>
          </div>,
          document.body,
        )}
        {introMode && (
          <div className={`intro-shell ${introFadingOut ? "fade-out" : ""} ${returningToIntro ? "entering" : ""} ${startupReveal ? "" : "startup-enter"}`}>
            <h1 className={startupReveal ? "intro-hero-fade-in" : "intro-hero-startup"}>Drop your resume. Start the hunt.</h1>
            <p className={startupReveal ? "intro-hero-fade-in" : "intro-hero-startup"}>Describe the role you want and I will search and score Linkedin's top matches.</p>

            <form className={`intro-composer ${startupReveal ? "intro-hero-fade-in" : "intro-hero-startup"}`} onSubmit={handleSubmit}>
              <div className={`composer-shell single-line ${resumePickerOpen ? "with-resume-strip" : ""}`}>
                <ResumePicker
                  uploads={resumeUploads}
                  open={resumePickerOpen}
                  closing={resumePlusClosing}
                  busy={busy}
                  activeResumeName={activeResumeName}
                  pulsingResumeName={pulsingResumeName}
                  apiBase={API_BASE}
                  onAddClick={handleAddResumeClick}
                  onSelect={handleSelectUploadedResume}
                  onDelete={handleDeleteUploadedResume}
                  onPlusMouseEnter={(event) => {
                    if (resumePickerOpen) {
                      showTopTooltip(event, "Upload another resume");
                    }
                  }}
                  onItemMouseEnter={(event, displayName) => {
                    if (resumePickerOpen) {
                      showTopTooltip(event, displayName);
                    }
                  }}
                  onItemMouseLeave={hideTooltip}
                  onAddMouseLeave={hideTooltip}
                />
                <div className="composer-main-row">
                  <div className={`resume-icon-stack ${resumePickerOpen ? "open" : ""}`}>
                    <button
                      type="button"
                      className={`upload-inline-button resume-toggle-button ${resumePickerOpen ? "open" : ""}`}
                      onClick={onResumeButtonClick}
                      onMouseEnter={(event) => {
                        showTopTooltip(event, resumePickerOpen ? "Close resumes" : getResumeToggleTooltipText());
                      }}
                      onMouseLeave={hideTooltip}
                      disabled={busy}
                      aria-label={hasResume ? "Toggle resumes" : "Upload resume"}
                    >
                      {hasResume ? (
                        <>
                          <ResumePresentIcon className="resume-status-icon" />
                          <FontAwesomeIcon icon={faXmark} className="resume-close-icon" />
                        </>
                      ) : (
                        <FontAwesomeIcon icon={faPlus} className="resume-empty-icon" />
                      )}
                    </button>
                  </div>

                  <textarea
                    ref={introTextareaRef}
                    className={`bottom-composer-textarea intro-suggestion-fade ${introSuggestionFadingOut ? "placeholder-fade-out" : ""}`}
                    value={query}
                    onChange={handleIntroTextareaChange}
                    onKeyDown={onComposerKeyDown}
                    spellCheck={false}
                    autoCorrect="off"
                    autoCapitalize="off"
                    autoComplete="off"
                    data-gramm="false"
                    data-gramm_editor="false"
                    data-enable-grammarly="false"
                    rows={1}
                    placeholder={introSuggestion}
                  />

                  <button
                    type="submit"
                    className="search-stop-button has-tooltip"
                    data-tooltip={busy ? "Stop prompt" : "Send prompt"}
                    aria-label={busy ? "Stop search" : "Run search"}
                    disabled={!busy && !canSubmitQuery}
                  >
                    <FontAwesomeIcon icon={busy ? faStop : faArrowUp} />
                  </button>
                </div>
              </div>
            </form>
          </div>
        )}
        <div className="chat-content" ref={chatContentRef}>
          {messages.map((message) => (
            <div
              key={message.id}
              className={`chat-message ${message.role === "user" ? "user" : "assistant"} ${message.className || ""}`}
              ref={(element) => { messageRefs.current[message.id] = element; }}
            >
              {message.type === "report" ? (
                <ReportPanel
                  report={message.report}
                  onEmailLatest={openEmailModal}
                  emailBusy={emailBusy}
                  onShowEmailTooltip={(event) => showBottomTooltip(event, "Send email")}
                  onHideTooltip={hideTooltip}
                  isMobileLayout={isMobileLayout}
                  panelRef={(element) => { reportPanelRefs.current[message.id] = element; }}
                />
              ) : (
                message.role === "user" ? (
                  <div className="search-user-message-stack">
                    <div className="user-bubble">{message.text}</div>
                    {message.isSearchMessage && (
                      <div className="search-resume-row">
                        <button
                          type="button"
                          className="search-resume-toggle"
                          onClick={() => setOpenResumeMessageId((prev) => (prev === message.id ? "" : message.id))}
                        >
                          <span>Resume</span>
                          <FontAwesomeIcon icon={faChevronUp} className={`search-resume-chevron ${openResumeMessageId === message.id ? "open" : ""}`} />
                        </button>
                        {message.resumeUsed && (
                          <div className={`search-resume-thumb-panel ${openResumeMessageId === message.id ? "open" : ""}`}>
                            <div
                              className="search-resume-thumb"
                              style={message.resumeUsed.thumbnail_url ? { backgroundImage: `url(${API_BASE}${message.resumeUsed.thumbnail_url})` } : undefined}
                              onMouseEnter={(event) => showResumeThumbTooltip(event, message.resumeUsed.name)}
                              onMouseLeave={hideResumeThumbTooltip}
                            >
                              {!message.resumeUsed.thumbnail_url && "PDF"}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="assistant-text">{message.text}</div>
                )
              )}
            </div>
          ))}

          {busy && (
            <div className="chat-message assistant">
              <div className="loading-status-row search-progress-panel">
                {searchStatusVisible && (searchDisplay.headline || searchDisplay.subline) ? (
                  <div key={searchStatusKey} className="search-progress-copy search-progress-fade">
                    {searchDisplay.headline && (
                      <div className={`search-progress-headline ${searchDisplay.shimmer ? "status-shimmer" : ""}`}>
                        {searchDisplay.headline}
                      </div>
                    )}
                    {searchDisplay.subline && (
                      <div key={searchDisplay.subline} className="search-progress-subline search-progress-subline-fade">
                        {searchDisplay.subline}
                      </div>
                    )}
                  </div>
                ) : (
                  <SafeLottie animationData={loadingAnimation} className="loading-lottie" />
                )}
              </div>
            </div>
          )}
        </div>

        <form
          ref={composerOverlayRef}
          className={`composer-overlay ${
            introMode ? (returningToIntro ? "to-intro" : "pre-docked") : "docked-in"
          }`}
          onSubmit={handleSubmit}
        >
          <div className={`composer-shell single-line ${resumePickerOpen ? "with-resume-strip" : ""}`}>
            <ResumePicker
              uploads={resumeUploads}
              open={resumePickerOpen}
              closing={resumePlusClosing}
              busy={busy}
              activeResumeName={activeResumeName}
              pulsingResumeName={pulsingResumeName}
              apiBase={API_BASE}
              onAddClick={handleAddResumeClick}
              onSelect={handleSelectUploadedResume}
              onDelete={handleDeleteUploadedResume}
              onPlusMouseEnter={(event) => {
                if (resumePickerOpen) {
                  showTopTooltip(event, "Upload another resume");
                }
              }}
              onItemMouseEnter={(event, displayName) => {
                if (resumePickerOpen) {
                  showTopTooltip(event, displayName);
                }
              }}
              onItemMouseLeave={hideTooltip}
              onAddMouseLeave={hideTooltip}
            />
            <div className="composer-main-row">
              <div className={`resume-icon-stack ${resumePickerOpen ? "open" : ""}`}>
                <button
                  type="button"
                  className={`upload-inline-button resume-toggle-button ${resumePickerOpen ? "open" : ""}`}
                  onClick={onResumeButtonClick}
                  onMouseEnter={(event) => {
                    showTopTooltip(event, resumePickerOpen ? "Close resumes" : getResumeToggleTooltipText());
                  }}
                  onMouseLeave={hideTooltip}
                  disabled={busy}
                  aria-label={hasResume ? "Toggle resumes" : "Upload resume"}
                >
                  {hasResume ? (
                    <>
                      <ResumePresentIcon className="resume-status-icon" />
                      <FontAwesomeIcon icon={faXmark} className="resume-close-icon" />
                    </>
                  ) : (
                    <FontAwesomeIcon icon={faPlus} className="resume-empty-icon" />
                  )}
                </button>
              </div>

              <textarea
                ref={bottomTextareaRef}
                className="bottom-composer-textarea"
                value={query}
                onChange={handleBottomTextareaChange}
                onKeyDown={onComposerKeyDown}
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
                autoComplete="off"
                data-gramm="false"
                data-gramm_editor="false"
                data-enable-grammarly="false"
                rows={1}
                placeholder="Type search query"
              />

              <button
                type="submit"
                className="search-stop-button has-tooltip"
                data-tooltip={busy ? "Stop prompt" : "Send prompt"}
                aria-label={busy ? "Stop search" : "Run search"}
                disabled={!busy && !canSubmitQuery}
              >
                <FontAwesomeIcon icon={busy ? faStop : faArrowUp} />
              </button>
            </div>
          </div>
        </form>
          {floatingTooltip.visible && createPortal(
            <div
            className={`floating-tooltip-left ${floatingTooltip.placement === "top" ? "floating-tooltip-top" : ""} ${floatingTooltip.placement === "right" ? "floating-tooltip-right" : ""} ${floatingTooltip.placement === "bottom" ? "floating-tooltip-bottom" : ""}`}
            style={{ top: `${floatingTooltip.top}px`, left: `${floatingTooltip.left}px` }}
          >
            {floatingTooltip.text}
          </div>,
          document.body,
        )}
        {resumeThumbTooltip.visible && createPortal(
          <div
            className="search-resume-tooltip"
            style={{ top: `${resumeThumbTooltip.top}px`, left: `${resumeThumbTooltip.left}px` }}
          >
            {resumeThumbTooltip.text}
          </div>,
          document.body,
        )}
        {emailModalOpen && createPortal(
          <div className="email-modal-backdrop" onClick={handleCancelEmailModal}>
            <div className="email-modal-card" onClick={(event) => event.stopPropagation()}>
              <h3 className="email-modal-title">Email Report</h3>
              <input
                className={`email-modal-input ${showEmailError ? "invalid" : ""}`}
                value={emailTo}
                onChange={(event) => setEmailTo(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    handleSendEmailFromModal();
                  }
                }}
                placeholder="recipient@example.com"
              />
              {showEmailError && <p className="email-modal-error">Enter a valid email</p>}
              <div className="email-modal-actions">
                <button
                  type="button"
                  className="email-modal-cancel"
                  onClick={handleCancelEmailModal}
                >
                  <FontAwesomeIcon icon={faXmark} />
                  <span>Cancel</span>
                </button>
                <button
                  type="button"
                  className="email-modal-send"
                  onClick={handleSendEmailFromModal}
                  disabled={emailBusy}
                >
                  <FontAwesomeIcon icon={faPaperPlane} />
                  <span>Send</span>
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
        {scheduleModalOpen && createPortal(
          <div className="schedule-modal-backdrop" onClick={handleCancelScheduleModal}>
            <div className="schedule-modal-card" onClick={(event) => event.stopPropagation()}>
              <div className="schedule-modal-header">
                <h3 className="schedule-modal-title">
                  <span>Schedule Job Search</span>
                </h3>
                <button
                  type="button"
                  className="modal-icon-close"
                  onClick={handleCancelScheduleModal}
                  aria-label="Close schedule modal"
                >
                  <FontAwesomeIcon icon={faCalendarDays} className="modal-header-icon modal-header-icon-primary" />
                  <FontAwesomeIcon icon={faXmark} className="modal-header-icon modal-header-icon-close" />
                </button>
              </div>
              <p className="schedule-modal-caption">
                Choose when automatic searches run and where scheduled reports should be sent.
              </p>
              <p className="schedule-timezone-note">
                Times use your local time zone: <span>{scheduleForm.timezone || getBrowserTimeZone()}</span>
              </p>
              {scheduleLoading ? (
                <p className="muted schedule-loading-message" key={scheduleLoadingMessage}>
                  <span className="schedule-loading-fade">{scheduleLoadingMessage}</span>
                </p>
              ) : (
                <>
                  <div className="schedule-row">
                    <span>Scheduler</span>
                    <button
                      type="button"
                      className={`schedule-toggle ${scheduleForm.enabled ? "on" : ""}`}
                      onClick={handleScheduleEnabledToggle}
                      aria-label={scheduleForm.enabled ? "Disable scheduler" : "Enable scheduler"}
                    >
                      <span className="schedule-toggle-thumb" />
                    </button>
                  </div>

                  <div className={`schedule-top-grid ${scheduleLocked ? "locked" : ""}`}>
                    <div className="schedule-field">
                      <label htmlFor="schedule-time">Run Time</label>
                      <input
                        id="schedule-time"
                        type="time"
                        value={scheduleForm.time}
                        disabled={scheduleLocked}
                        onChange={(event) => setScheduleForm((previous) => ({ ...previous, time: event.target.value }))}
                      />
                    </div>

                    <div className="schedule-field">
                      <div className="schedule-daily-title">Daily</div>
                      <div className="schedule-days-row">
                        <div className="schedule-days schedule-daily-days">
                          <button
                            type="button"
                            className={`schedule-day schedule-daily-toggle ${scheduleDailyEnabled ? "active" : ""}`}
                            onClick={toggleDailyDays}
                            disabled={scheduleLocked}
                          >
                            {scheduleDailyEnabled ? "On" : "Off"}
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="schedule-field">
                      <label>Days</label>
                      <div className="schedule-days-row">
                        <div className="schedule-days">
                          {SCHEDULE_DAYS.map((day) => (
                            <button
                              key={day.key}
                              type="button"
                              className={`schedule-day ${scheduleForm.days[day.key] ? "active" : ""}`}
                              onClick={() => toggleScheduleDay(day.key)}
                              disabled={scheduleLocked}
                            >
                              {day.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className={`schedule-field ${scheduleLocked ? "locked" : ""}`}>
                    <label htmlFor="schedule-keywords">Search Query</label>
                    <input
                      id="schedule-keywords"
                      type="text"
                      value={scheduleForm.keywords}
                      disabled={scheduleLocked}
                      onChange={(event) => setScheduleForm((previous) => ({ ...previous, keywords: event.target.value }))}
                      placeholder="Target industry"
                    />
                  </div>

                  <div className={`schedule-grid ${scheduleLocked ? "locked" : ""}`}>
                    <div className="schedule-field">
                      <label htmlFor="schedule-location">Location</label>
                      <input
                        id="schedule-location"
                        type="text"
                        value={scheduleForm.location}
                        disabled={scheduleLocked}
                        onChange={(event) => setScheduleForm((previous) => ({ ...previous, location: event.target.value }))}
                        placeholder="United States"
                      />
                    </div>
                    <div className="schedule-field">
                      <label htmlFor="schedule-pages">Pages</label>
                      <input
                        id="schedule-pages"
                        type="text"
                        inputMode="numeric"
                        value={scheduleForm.pages}
                        disabled={scheduleLocked}
                        onKeyDown={(event) => {
                          if (
                            event.ctrlKey ||
                            event.metaKey ||
                            event.altKey ||
                            [
                              "Backspace",
                              "Delete",
                              "ArrowLeft",
                              "ArrowRight",
                              "ArrowUp",
                              "ArrowDown",
                              "Tab",
                              "Home",
                              "End",
                              "Enter",
                            ].includes(event.key)
                          ) {
                            return;
                          }
                          if (!/^[0-9]$/.test(event.key)) {
                            event.preventDefault();
                            return;
                          }
                          if (!/^[1-4]$/.test(event.key)) {
                            event.preventDefault();
                            return;
                          }
                          event.preventDefault();
                          setScheduleForm((previous) => ({ ...previous, pages: event.key }));
                        }}
                        onPaste={(event) => {
                          event.preventDefault();
                          const pastedText = event.clipboardData.getData("text");
                          const normalizedValue = normalizeSchedulePagesInput(pastedText);
                          if (normalizedValue !== "") {
                            setScheduleForm((previous) => ({ ...previous, pages: normalizedValue }));
                          } else {
                            setScheduleForm((previous) => ({ ...previous, pages: "1" }));
                          }
                        }}
                        onChange={(event) => {
                          const normalizedValue = normalizeSchedulePagesInput(event.target.value);
                          if (normalizedValue !== "") {
                            setScheduleForm((previous) => ({ ...previous, pages: normalizedValue }));
                          }
                        }}
                        onBlur={(event) => {
                          const normalizedValue = normalizeSchedulePagesInput(event.target.value) || "1";
                          setScheduleForm((previous) => ({ ...previous, pages: normalizedValue }));
                        }}
                      />
                    </div>
                  </div>

                  <div className={`schedule-field ${scheduleLocked ? "locked" : ""}`}>
                    <label htmlFor="schedule-email-to">Email To</label>
                    <input
                      id="schedule-email-to"
                      className={showScheduleEmailValidation ? "invalid" : ""}
                      type="text"
                      value={scheduleForm.email_to}
                      disabled={scheduleLocked}
                      onChange={(event) => setScheduleForm((previous) => ({ ...previous, email_to: event.target.value }))}
                      placeholder="recipient@example.com"
                    />
                    {showScheduleEmailValidation && <p className="schedule-modal-error">Enter a valid email</p>}
                  </div>
                </>
              )}

              <div className="schedule-modal-actions">
                <button
                  type="button"
                  className="schedule-modal-cancel"
                  onClick={handleCancelScheduleModal}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="schedule-modal-save"
                  onClick={handleSaveSchedule}
                  disabled={scheduleLoading || scheduleSaving}
                >
                  {scheduleSaving ? "Saving..." : "Save Schedule"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
        </div>
      </section>
    </main>
    <Analytics />
    <SpeedInsights />
    </>
  );
}
