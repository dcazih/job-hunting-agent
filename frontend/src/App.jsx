import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowUp,
  faChevronUp,
  faCrosshairs,
  faCircleUser,
  faChevronDown,
  faEllipsis,
  faEnvelope,
  faFile,
  faFileArrowUp,
  faCheck,
  faCalendarDays,
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
  days: {
    mon: true,
    tue: true,
    wed: true,
    thu: true,
    fri: true,
    sat: false,
    sun: false,
  },
  keywords: "software engineer",
  location: "United States",
  pages: 2,
  email_to: "",
};

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

function JobCard({ job }) {
  const score = Number(job.score || 0);

  return (
    <article className="job-card">
      <div className="job-card-header">
        <h4>{job.title || "Untitled role"}</h4>
        <div className="job-score-pill" aria-label={`Score ${score} out of 100`}>
          <span className="job-score-value">{score}</span>
          <span className="job-score-total">/100</span>
        </div>
      </div>
      <div className="job-card-submeta">
        <p className="job-meta">{job.company || "Unknown company"}</p>
        <p className="job-meta">{job.location || "Unknown location"}</p>
      </div>
      <p className="job-fit">{job.fit_summary || "No summary provided."}</p>
      <a className="job-link" href={job.url} target="_blank" rel="noreferrer">Open listing</a>
    </article>
  );
}

function ReportPanel({ report, onEmailLatest, emailBusy, onShowEmailTooltip, onHideTooltip }) {
  if (!report) return <p className="assistant-text">No report selected.</p>;
  const [remainingOpen, setRemainingOpen] = useState(false);

  const topJobs = report.top_jobs || [];
  const remainingJobs = report.remaining_jobs || [];
  const title = report.report_name || report.report_path?.split("/").pop() || "Untitled";
  const targetIndustry = report.target_industry || "";

  return (
    <section className="report-panel">
      <div className="report-panel-header">
        <h3>
          <span className="report-label">Report:&nbsp;&nbsp;</span>
          <span className="report-title">{`${title}`}</span>
        </h3>
        <button
          disabled={emailBusy}
          onClick={onEmailLatest}
          onMouseEnter={onShowEmailTooltip}
          onMouseLeave={onHideTooltip}
          aria-label="Send report email"
          className=""
        >
          <FontAwesomeIcon icon={faEnvelope} />
        </button>
      </div>
      {targetIndustry && <p className="report-target-industry">Target industry: {targetIndustry}</p>}

      <section className="report-section">
        <h4>Top Jobs</h4>
        <div className="jobs-row">
          {topJobs.length > 0 ? topJobs.map((job) => (
            <JobCard key={job.job_id || job.url} job={job} />
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
              <JobCard key={job.job_id || job.url} job={job} />
            )) : <p className="assistant-text">No remaining jobs in this report.</p>}
          </div>
        </div>
      </section>
    </section>
  );
}

function formatSearchStep(step) {
  const normalized = String(step || "").toLowerCase();
  if (
    normalized.includes("scraping jobs") ||
    normalized.includes("filtering seen jobs") ||
    normalized.includes("loading profile") ||
    normalized.includes("loading memory") ||
    normalized.includes("fetch")
  ) return "Fetching Jobs";
  if (normalized.includes("description")) return "Getting Descriptions";
  if (normalized.includes("scoring jobs") || normalized.includes("score")) return "Scoring Jobs";
  if (normalized.includes("building report") || normalized.includes("report")) return "Creating Report";
  return "";
}

function isSearchIntent(message) {
  const text = String(message || "").trim().toLowerCase();
  return /^(run|search|hunt|start search|start hunt|find jobs)\b/.test(text);
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

export default function App() {
  const loadingWords = [
    "Working",
    "Seeking",
    "Inquiring",
    "Rummaging",
    "Digging",
    "Sniffing Around",
    "Treasure Hunting",
    "Sifting",
    "Poking Around",
    "Deep Diving",
    "Sherlocking",
    "Job Goblining",
    "Opportunity Fishing",
    "Prospecting",
    "Scavenging",
    "Radar Sweeping",
    "Dusting for Leads",
    "Chasing Leads",
  ];
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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
  const [runId, setRunId] = useState("");
  const [runState, setRunState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailTo, setEmailTo] = useState("");
  const [showEmailValidation, setShowEmailValidation] = useState(false);
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleSaving, setScheduleSaving] = useState(false);
  const [scheduleForm, setScheduleForm] = useState(DEFAULT_SCHEDULE);
  const [scheduleDailyEnabled, setScheduleDailyEnabled] = useState(false);
  const [showScheduleEmailValidation, setShowScheduleEmailValidation] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileResumeListOpen, setProfileResumeListOpen] = useState(false);
  const [profileTargetIndustry, setProfileTargetIndustry] = useState("");
  const [profilePreferences, setProfilePreferences] = useState("");
  const [scheduleToastVisible, setScheduleToastVisible] = useState(false);
  const [openResumeMessageId, setOpenResumeMessageId] = useState("");
  const [resumeThumbTooltip, setResumeThumbTooltip] = useState({ visible: false, text: "", top: 0, left: 0 });
  const [introMode, setIntroMode] = useState(true);
  const [introFadingOut, setIntroFadingOut] = useState(false);
  const [returningToIntro, setReturningToIntro] = useState(false);
  const [hasResume, setHasResume] = useState(false);
  const [resumeUploads, setResumeUploads] = useState([]);
  const [resumePickerOpen, setResumePickerOpen] = useState(false);
  const [resumePlusClosing, setResumePlusClosing] = useState(false);
  const [floatingTooltip, setFloatingTooltip] = useState({ visible: false, text: "", top: 0, left: 0, placement: "left" });
  const [pulsingResumeName, setPulsingResumeName] = useState("");
  const [randomLoadingWord, setRandomLoadingWord] = useState("Searching");

  const messageRefs = useRef({});
  const chatContentRef = useRef(null);
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
  const chatAbortRef = useRef(null);
  const stopRequestedRef = useRef(false);
  const runIdRef = useRef("");
  const bottomTextareaHeightRef = useRef(0);

  useEffect(() => {
    runIdRef.current = runId;
  }, [runId]);

  useEffect(() => {
    if (runState?.status !== "running") return;
    const timer = setInterval(() => {
      const next = loadingWords[Math.floor(Math.random() * loadingWords.length)];
      setRandomLoadingWord(next);
    }, 8500);
    return () => clearInterval(timer);
  }, [runState?.status]);

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
    let timer = null;

    if (runId) {
      timer = setInterval(async () => {
        try {
          const status = await api(`/api/search/status/${runId}`);
          setRunState(status);

          if (status.status === "complete" || status.status === "failed") {
            clearInterval(timer);
            setBusy(false);
            stopRequestedRef.current = false;

            if (status.status === "complete") {
              setSelectedReportPath(status.result.report_path);
              upsertReportMessage(status.result, true);
              await refreshReports();
            } else {
              appendText(status.error || "Search failed.");
            }
            setRunId("");
          }
        } catch (error) {
          clearInterval(timer);
          setBusy(false);
          setRunId("");
          stopRequestedRef.current = false;
          appendText(error.message);
        }
      }, 2000);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (!focusRequest?.id) return;
    const target = messageRefs.current[focusRequest.id];
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: focusRequest.block || "end" });
    }
  }, [focusRequest, messages]);

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
  }, [messages, runState, introMode, resumePickerOpen]);

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
        target.closest(".resume-picker-strip") ||
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
      if (chatAbortRef.current) {
        chatAbortRef.current.abort();
      }
    };
  }, []);

  async function loadReport(reportPath) {
    try {
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
      appendText(`Resume uploaded. Extracted ${payload.characters_extracted} characters.`);
    } catch (error) {
      appendText(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSearch() {
    const trimmed = query.trim();
    if (!trimmed || busy) return;
    stopRequestedRef.current = false;
    const searchIntent = isSearchIntent(trimmed);
    const activeResume = resumeUploads.find((item) => item.is_active) || null;

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
      searchIntent
        ? {
            isSearchMessage: true,
            resumeUsed: activeResume
              ? {
                  name: activeResume.display_name,
                  thumbnail_url: activeResume.thumbnail_url,
                }
              : null,
          }
        : {},
    );
    setQuery("");
    requestAnimationFrame(() => {
      resizeBottomComposerTextarea();
    });
    setBusy(true);

    try {
      if (!searchIntent) {
        const abortController = new AbortController();
        chatAbortRef.current = abortController;
        const payload = await api("/api/chat", {
          method: "POST",
          body: JSON.stringify({ message: trimmed }),
          signal: abortController.signal,
        });
        chatAbortRef.current = null;
        appendText(payload.assistant_message || "Done.", "assistant", "start");
        setBusy(false);
        return;
      }

      setRandomLoadingWord("Performing Job Search");
      setRunState({ status: "running", step: "Fetching jobs", progress: 0 });
      const abortController = new AbortController();
      chatAbortRef.current = abortController;
      const payload = await api("/api/search/run", {
        method: "POST",
        body: JSON.stringify({
          keywords: trimmed,
          location: "United States",
          pages: 2,
        }),
        signal: abortController.signal,
      });
      chatAbortRef.current = null;
      if (!payload.run_id) {
        throw new Error("Search did not return a run id.");
      }
      setRunId(payload.run_id);
      if (stopRequestedRef.current) {
        try {
          await api(`/api/search/stop/${payload.run_id}`, { method: "POST" });
        } catch {
          // If stop fails here, the polling loop will surface run failure/timeout.
        }
      }
    } catch (error) {
      chatAbortRef.current = null;
      setBusy(false);
      setRunState(null);
      if (error?.name === "AbortError") {
        appendText("Stopped.");
        return;
      }
      appendText(error.message);
    }
  }

  async function handleStop() {
    stopRequestedRef.current = true;
    if (chatAbortRef.current) {
      chatAbortRef.current.abort();
    }
    const activeRunId = runIdRef.current;
    if (!activeRunId) {
      setBusy(false);
      return;
    }
    try {
      await api(`/api/search/stop/${activeRunId}`, { method: "POST" });
      setBusy(false);
    } catch (error) {
      appendText(error.message);
    }
  }

  function openEmailModal() {
    setEmailModalOpen(true);
    setShowEmailValidation(false);
  }

  async function openProfileModal() {
    setProfileModalOpen(true);
    setProfileResumeListOpen(true);
    setProfileLoading(true);
    try {
      const payload = await api("/api/preferences");
      const text = String(payload?.preferences || "");
      setProfilePreferences(text);
      const firstLine = text.split("\n").find((line) => line.trim()) || "";
      setProfileTargetIndustry(firstLine);
    } catch (error) {
      appendText(error.message);
      setProfilePreferences("");
      setProfileTargetIndustry("");
    } finally {
      setProfileLoading(false);
    }
  }

  function closeProfileModal() {
    setProfileModalOpen(false);
    setProfileResumeListOpen(false);
  }

  async function handleSaveProfile() {
    const next = profilePreferences.trim();
    if (!next) {
      appendText("Preferences text cannot be empty.");
      return;
    }
    setProfileSaving(true);
    try {
      await api("/api/preferences", {
        method: "POST",
        body: JSON.stringify({ preferences: next }),
      });
      setProfileModalOpen(false);
      setProfileResumeListOpen(false);
    } catch (error) {
      appendText(error.message);
    } finally {
      setProfileSaving(false);
    }
  }

  function normalizeSchedulePayload(payload) {
    return {
      enabled: Boolean(payload?.enabled),
      time: String(payload?.time || DEFAULT_SCHEDULE.time),
      days: {
        mon: Boolean(payload?.days?.mon),
        tue: Boolean(payload?.days?.tue),
        wed: Boolean(payload?.days?.wed),
        thu: Boolean(payload?.days?.thu),
        fri: Boolean(payload?.days?.fri),
        sat: Boolean(payload?.days?.sat),
        sun: Boolean(payload?.days?.sun),
      },
      keywords: String(payload?.keywords || DEFAULT_SCHEDULE.keywords),
      location: String(payload?.location || DEFAULT_SCHEDULE.location),
      pages: Number(payload?.pages || DEFAULT_SCHEDULE.pages),
      email_to: String(payload?.email_to || DEFAULT_SCHEDULE.email_to),
    };
  }

  async function openScheduleModal() {
    setScheduleModalOpen(true);
    setShowScheduleEmailValidation(false);
    setScheduleLoading(true);
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
    }
  }

  function handleCancelScheduleModal() {
    setScheduleModalOpen(false);
    setShowScheduleEmailValidation(false);
  }

  function toggleScheduleDay(dayKey) {
    setScheduleDailyEnabled(false);
    setScheduleForm((previous) => ({
      ...previous,
      days: {
        ...previous.days,
        [dayKey]: !previous.days[dayKey],
      },
    }));
  }

  function toggleDailyDays() {
    setScheduleDailyEnabled((previous) => {
      const next = !previous;
      if (next) {
        setScheduleForm((current) => ({
          ...current,
          days: {
            mon: true,
            tue: true,
            wed: true,
            thu: true,
            fri: true,
            sat: true,
            sun: true,
          },
        }));
      }
      return next;
    });
  }

  async function handleSaveSchedule() {
    const hasDayEnabled = Object.values(scheduleForm.days).some(Boolean);
    if (!hasDayEnabled && scheduleForm.enabled) {
      appendText("Enable at least one day for the scheduler.");
      return;
    }
    const trimmedScheduleEmail = scheduleForm.email_to.trim();
    if (trimmedScheduleEmail && !EMAIL_REGEX.test(trimmedScheduleEmail)) {
      setShowScheduleEmailValidation(true);
      return;
    }

    setShowScheduleEmailValidation(false);
    setScheduleSaving(true);
    try {
      const payload = await api("/api/schedule", {
        method: "POST",
        body: JSON.stringify({ ...scheduleForm, email_to: trimmedScheduleEmail }),
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
      }, 1800);
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
    const rect = event.currentTarget.getBoundingClientRect();
    setFloatingTooltip({
      visible: true,
      text,
      top: rect.top - 8,
      left: rect.left + rect.width / 2,
      placement: "top",
    });
  }

  function showRightTooltip(event, text) {
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

  function handleNewHunt() {
    if (introMode) return;

    setReturningToIntro(true);
    setIntroMode(true);
    setIntroFadingOut(false);
    setQuery("");
    setRunId("");
    setRunState(null);
    stopRequestedRef.current = false;
    setBusy(false);
    setOpenReportMenu("");
    setMessages([]);

    setTimeout(() => {
      setReturningToIntro(false);
    }, 320);
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
      handleStop();
    } else {
      handleSearch();
    }
  }

  function onComposerKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  }

  function animateBottomTextareaToContent(textarea) {
    if (!textarea) return;
    const current = textarea.getBoundingClientRect().height;
    textarea.style.height = "auto";
    const natural = textarea.scrollHeight;
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
    function handleWindowResize() {
      resizeBottomComposerTextarea();
      resizeIntroComposerTextarea();
    }
    window.addEventListener("resize", handleWindowResize);
    return () => window.removeEventListener("resize", handleWindowResize);
  }, []);

  const trimmedEmail = emailTo.trim();
  const isEmailValid = EMAIL_REGEX.test(trimmedEmail);
  const showEmailError = showEmailValidation && !isEmailValid;
  const mappedRunningStatus = formatSearchStep(runState?.step);
  const runningStepNormalized = String(runState?.step || "").toLowerCase();
  const runningStatusText = runningStepNormalized.includes("fetch")
    ? `${randomLoadingWord}...`
    : mappedRunningStatus;
  const scheduleLocked = !scheduleForm.enabled;

  return (
    <main className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : "sidebar-open"} ${sidebarAnimating ? "tooltips-disabled" : ""}`}>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="visually-hidden-file-input"
        onChange={handleResumeInputChange}
      />
      <aside className={`sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        <div className="sidebar-top">
          <div className="brand-box" aria-hidden={sidebarCollapsed}>
            <h2>Job-Hunting Agent</h2>
          </div>

          <button
            className="icon-button sidebar-toggle has-tooltip sidebar-tooltip-side"
            data-tooltip={sidebarCollapsed ? "Open sidebar" : "Collapse sidebar"}
            aria-label={sidebarCollapsed ? "Open sidebar" : "Collapse sidebar"}
            onMouseEnter={() => {
              if (sidebarCollapsed && collapsedHoverArmed) {
                setCollapsedHoverActive(true);
              }
            }}
            onMouseLeave={() => {
              if (sidebarCollapsed) {
                setCollapsedHoverActive(false);
                setCollapsedHoverArmed(true);
              }
            }}
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
                if (next) {
                  setCollapsedHoverArmed(false);
                  setCollapsedHoverActive(false);
                } else {
                  setCollapsedHoverArmed(false);
                  setCollapsedHoverActive(false);
                }
                return next;
              });
            }}
          >
            {!sidebarCollapsed && <FontAwesomeIcon icon={faRightToBracket} rotation={180} />}
            {sidebarCollapsed && (
              <span className={`collapsed-toggle-icons ${collapsedHoverActive ? "hover-active" : ""}`}>
                <FontAwesomeIcon icon={faCrosshairs} className="bullseye-icon" />
                <FontAwesomeIcon icon={faRightToBracket} className="open-icon" />
              </span>
            )}
          </button>
        </div>

        <div className="sidebar-actions">
          <button
            className={`profile-button sidebar-action-button ${sidebarCollapsed ? "has-tooltip sidebar-collapsed-tooltip" : ""}`}
            data-tooltip={sidebarCollapsed ? "New Hunt" : ""}
            onClick={handleNewHunt}
          >
            <FontAwesomeIcon icon={faPenToSquare} className="sidebar-action-icon" />
            <span className={`profile-text sidebar-action-text ${sidebarCollapsed ? "hidden" : ""}`}>New Hunt</span>
          </button>
          <button
            className={`profile-button sidebar-action-button ${sidebarCollapsed ? "has-tooltip sidebar-collapsed-tooltip" : ""}`}
            data-tooltip={sidebarCollapsed ? "Schedule" : ""}
            onClick={openScheduleModal}
          >
            <FontAwesomeIcon icon={faCalendarDays} className="sidebar-action-icon" />
            <span className={`profile-text sidebar-action-text ${sidebarCollapsed ? "hidden" : ""}`}>Schedule</span>
          </button>
          <div ref={sidebarSearchRef} className="sidebar-search-wrap">
            <button
              className={`profile-button sidebar-action-button ${sidebarCollapsed ? "has-tooltip sidebar-collapsed-tooltip" : ""}`}
              data-tooltip={sidebarCollapsed ? "Search" : ""}
              onClick={handleSidebarSearchClick}
            >
              <FontAwesomeIcon icon={faMagnifyingGlass} className="sidebar-action-icon" />
              {!sidebarSearchActive && (
                <span className={`profile-text sidebar-action-text ${sidebarCollapsed ? "hidden" : ""}`}>Search</span>
              )}
              {sidebarSearchActive && !sidebarCollapsed && (
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

        {!sidebarCollapsed && <h3 className="report-list-title">Reports</h3>}
        <div className="report-list">
          {filteredReports.length === 0 && !sidebarCollapsed && <p className="muted">No reports found.</p>}

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
                {sidebarCollapsed ? "•" : item.name}
              </button>

              {!sidebarCollapsed && (
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
            </div>
          ))}
        </div>

        <div className="sidebar-bottom">
          <button
            className={`profile-button ${sidebarCollapsed ? "has-tooltip sidebar-collapsed-tooltip" : ""}`}
            data-tooltip={sidebarCollapsed ? "Profile" : ""}
            aria-label="Profile"
            onClick={openProfileModal}
          >
            <FontAwesomeIcon icon={faCircleUser} className="profile-icon" />
            <span className={`profile-text ${sidebarCollapsed ? "hidden" : ""}`}>Profile</span>
          </button>
        </div>
      </aside>

      <section className="chat-layout" onClick={() => setOpenReportMenu("")}>
        {scheduleToastVisible && (
          <div className="schedule-save-toast" role="status" aria-live="polite">
            <span>Schedule saved</span>
            <span className="schedule-save-toast-icon">
              <FontAwesomeIcon icon={faCheck} />
            </span>
          </div>
        )}
        <div className={`chat-column ${introMode ? "intro-mode" : "docked-mode"}`}>
        {introMode && (
          <div className={`intro-shell ${introFadingOut ? "fade-out" : ""} ${returningToIntro ? "entering" : ""}`}>
            <h1>Drop a resume. Start the hunt.</h1>
            <p>Describe your target industry and I will search, score, and report top matches.</p>

            <form className="intro-composer" onSubmit={handleSubmit}>
              <div className={`composer-shell single-line ${resumePickerOpen ? "with-resume-strip" : ""}`}>
                <div className={`resume-picker-strip ${resumePickerOpen ? "open" : ""}`}>
                  <div className="resume-picker-scroll">
                    {resumeUploads.length > 0 && (resumePickerOpen || resumePlusClosing) && (
                      <button
                        type="button"
                        className="resume-plus "
                        onClick={handleAddResumeClick}
                        onMouseEnter={(event) => {
                          if (resumePickerOpen) {
                            showLeftTooltip(event, "Upload another resume");
                          }
                        }}
                        onMouseLeave={hideTooltip}
                        disabled={busy && !runId}
                        aria-label="Upload another resume"
                      >
                        <FontAwesomeIcon icon={faPlus} />
                      </button>
                    )}
                    {resumeUploads.map((item, index) => (
                      <div key={item.name} className="resume-chip-wrap">
                        {(() => {
                          const thumbSrc = item.thumbnail_url ? `${API_BASE}${item.thumbnail_url}` : "";
                          return (
                        <button
                          type="button"
                          className={`resume-chip ${item.is_active ? "active" : ""} ${pulsingResumeName === item.name ? "pulse" : ""}`}
                          aria-label={item.display_name}
                          onClick={() => handleSelectUploadedResume(item.name)}
                          style={thumbSrc ? { backgroundImage: `url(${thumbSrc})` } : undefined}
                          onMouseEnter={(event) => {
                            if (resumePickerOpen) {
                              showTopTooltip(event, item.display_name);
                            }
                          }}
                          onMouseLeave={hideTooltip}
                        >
                          {index + 1}
                        </button>
                          );
                        })()}
                        <button
                          type="button"
                          className="resume-chip-delete"
                          aria-label={`Delete ${item.display_name}`}
                          onClick={() => handleDeleteUploadedResume(item.name)}
                        >
                          <FontAwesomeIcon icon={faXmark} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="composer-main-row">
                  <div className={`resume-icon-stack ${resumePickerOpen ? "open" : ""}`}>
                    <button
                      type="button"
                      className={`upload-inline-button resume-toggle-button ${resumePickerOpen ? "open" : ""}`}
                      onClick={onResumeButtonClick}
                      onMouseEnter={(event) => {
                        if (resumePickerOpen) {
                          showLeftTooltip(event, "Close resumes");
                        }
                      }}
                      onMouseLeave={hideTooltip}
                      disabled={busy && !runId}
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
                    className="bottom-composer-textarea"
                    value={query}
                    onChange={handleIntroTextareaChange}
                    onKeyDown={onComposerKeyDown}
                    rows={1}
                    placeholder="Type search query"
                  />

                  <button
                    type="submit"
                    className="search-stop-button has-tooltip"
                    data-tooltip={busy ? "Stop prompt" : "Send prompt"}
                    aria-label={busy ? "Stop search" : "Run search"}
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
              className={`chat-message ${message.role === "user" ? "user" : "assistant"}`}
              ref={(element) => { messageRefs.current[message.id] = element; }}
            >
              {message.type === "report" ? (
                <ReportPanel
                  report={message.report}
                  onEmailLatest={openEmailModal}
                  emailBusy={emailBusy}
                  onShowEmailTooltip={(event) => showRightTooltip(event, "Send email")}
                  onHideTooltip={hideTooltip}
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

          {runState?.status === "running" && (
            <div className="chat-message assistant">
              <div className="loading-status-row">
                {runningStatusText ? (
                  <div className="assistant-text status-shimmer">{runningStatusText}</div>
                ) : (
                  <SafeLottie animationData={loadingAnimation} className="loading-lottie" />
                )}
              </div>
            </div>
          )}

          {busy && runState?.status !== "running" && (
            <div className="chat-message assistant">
              <div className="loading-status-row">
                <SafeLottie animationData={loadingAnimation} className="loading-lottie" />
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
            <div className={`resume-picker-strip ${resumePickerOpen ? "open" : ""}`}>
              <div className="resume-picker-scroll">
                {resumeUploads.length > 0 && (resumePickerOpen || resumePlusClosing) && (
                  <button
                    type="button"
                    className="resume-plus "
                    onClick={handleAddResumeClick}
                    onMouseEnter={(event) => {
                      if (resumePickerOpen) {
                        showLeftTooltip(event, "Upload another resume");
                      }
                    }}
                    onMouseLeave={hideTooltip}
                    disabled={busy && !runId}
                    aria-label="Upload another resume"
                  >
                    <FontAwesomeIcon icon={faPlus} />
                  </button>
                )}
                {resumeUploads.map((item, index) => (
                  <div key={item.name} className="resume-chip-wrap">
                    {(() => {
                      const thumbSrc = item.thumbnail_url ? `${API_BASE}${item.thumbnail_url}` : "";
                      return (
                    <button
                      type="button"
                      className={`resume-chip ${item.is_active ? "active" : ""} ${pulsingResumeName === item.name ? "pulse" : ""}`}
                      aria-label={item.display_name}
                      onClick={() => handleSelectUploadedResume(item.name)}
                      style={thumbSrc ? { backgroundImage: `url(${thumbSrc})` } : undefined}
                      onMouseEnter={(event) => {
                        if (resumePickerOpen) {
                          showTopTooltip(event, item.display_name);
                        }
                      }}
                      onMouseLeave={hideTooltip}
                    >
                      {index + 1}
                    </button>
                      );
                    })()}
                    <button
                      type="button"
                      className="resume-chip-delete"
                      aria-label={`Delete ${item.display_name}`}
                      onClick={() => handleDeleteUploadedResume(item.name)}
                    >
                      <FontAwesomeIcon icon={faXmark} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <div className="composer-main-row">
              <div className={`resume-icon-stack ${resumePickerOpen ? "open" : ""}`}>
                <button
                  type="button"
                  className={`upload-inline-button resume-toggle-button ${resumePickerOpen ? "open" : ""}`}
                  onClick={onResumeButtonClick}
                  onMouseEnter={(event) => {
                    if (resumePickerOpen) {
                      showLeftTooltip(event, "Close resumes");
                    }
                  }}
                  onMouseLeave={hideTooltip}
                  disabled={busy && !runId}
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
                rows={1}
                placeholder="Type search query"
              />

              <button
                type="submit"
                className="search-stop-button has-tooltip"
                data-tooltip={busy ? "Stop prompt" : "Send prompt"}
                aria-label={busy ? "Stop search" : "Run search"}
              >
                <FontAwesomeIcon icon={busy ? faStop : faArrowUp} />
              </button>
            </div>
          </div>
        </form>
        {floatingTooltip.visible && createPortal(
          <div
            className={`floating-tooltip-left ${floatingTooltip.placement === "top" ? "floating-tooltip-top" : ""} ${floatingTooltip.placement === "right" ? "floating-tooltip-right" : ""}`}
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
              <h3 className="schedule-modal-title">
                <FontAwesomeIcon icon={faCalendarDays} />
                <span>Schedule Job Search</span>
              </h3>
              <p className="schedule-modal-caption">
                Choose when automatic searches run and where scheduled reports should be sent.
              </p>
              {scheduleLoading ? (
                <p className="muted">Loading schedule...</p>
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

                    <div className="schedule-field schedule-daily-field">
                      <div className="schedule-daily-title">Daily</div>
                      <div className="schedule-daily-box">
                        <button
                          type="button"
                          className={`schedule-daily-toggle ${scheduleDailyEnabled ? "on" : ""}`}
                          onClick={toggleDailyDays}
                          disabled={scheduleLocked}
                        >
                          {scheduleDailyEnabled ? "On" : "Off"}
                        </button>
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
                      placeholder="software engineer"
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
                        type="number"
                        min={1}
                        max={10}
                        value={scheduleForm.pages}
                        disabled={scheduleLocked}
                        onChange={(event) => {
                          const next = Number(event.target.value || 1);
                          setScheduleForm((previous) => ({ ...previous, pages: Math.min(10, Math.max(1, next)) }));
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
        {profileModalOpen && createPortal(
          <div className="schedule-modal-backdrop" onClick={closeProfileModal}>
            <div className="schedule-modal-card profile-modal-card" onClick={(event) => event.stopPropagation()}>
              <div className="profile-modal-header">
                <h3 className="schedule-modal-title">
                  <FontAwesomeIcon icon={faCircleUser} />
                  <span>Profile</span>
                </h3>
                <button type="button" className="profile-modal-close" onClick={closeProfileModal} aria-label="Close profile modal">
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </div>
              <p className="schedule-modal-caption">Edit your search profile.</p>
              {profileLoading ? (
                <p className="muted">Loading profile...</p>
              ) : (
                <>
                  <div className="schedule-field">
                    <label>Resumes</label>
                    <div className={`resume-picker-strip profile-resume-strip ${profileResumeListOpen ? "open" : ""}`}>
                      <div className="resume-picker-scroll">
                        {resumeUploads.map((item, index) => (
                          <button
                            key={item.name}
                            type="button"
                            className={`resume-chip ${item.is_active ? "active" : ""}`}
                            onClick={() => handleSelectUploadedResume(item.name)}
                            onMouseEnter={(event) => showTopTooltip(event, item.display_name || item.name)}
                            onMouseLeave={hideTooltip}
                          >
                            <span>{index + 1}</span>
                          </button>
                        ))}
                        {profileResumeListOpen && (
                          <button type="button" className="resume-plus profile-resume-plus" onClick={handleAddResumeClick} aria-label="Upload another resume">
                            <FontAwesomeIcon icon={faPlus} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="schedule-field">
                    <label htmlFor="profile-target-industry">Target Industry</label>
                    <input
                      id="profile-target-industry"
                      type="text"
                      value={profileTargetIndustry}
                      onChange={(event) => setProfileTargetIndustry(event.target.value)}
                      placeholder="Software / AI / Fintech"
                    />
                  </div>

                  <div className="schedule-field">
                    <label htmlFor="profile-preferences">Preferences (Field, Location, Experience, etc.)</label>
                    <textarea
                      id="profile-preferences"
                      className="profile-preferences-box"
                      value={profilePreferences}
                      onChange={(event) => setProfilePreferences(event.target.value)}
                      placeholder="Your search preferences..."
                    />
                  </div>
                </>
              )}

              <div className="schedule-modal-actions">
                <button type="button" className="schedule-modal-cancel" onClick={closeProfileModal}>Cancel</button>
                <button type="button" className="schedule-modal-save" onClick={handleSaveProfile} disabled={profileLoading || profileSaving}>
                  {profileSaving ? "Saving..." : "Save Profile"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
        </div>
      </section>
    </main>
  );
}
