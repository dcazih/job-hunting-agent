import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faArrowUp,
  faCrosshairs,
  faCircleUser,
  faChevronDown,
  faEllipsis,
  faEnvelope,
  faFile,
  faFileArrowUp,
  faCheck,
  faMagnifyingGlass,
  faPaperPlane,
  faPenToSquare,
  faPlus,
  faRightToBracket,
  faStop,
  faXmark,
} from "@fortawesome/free-solid-svg-icons";

const API_BASE = import.meta.env.VITE_API_BASE || (import.meta.env.DEV ? "http://localhost:8000" : "");
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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

function JobCard({ job }) {
  return (
    <article className="job-card">
      <div className="job-card-header">
        <h4>{job.title || "Untitled role"}</h4>
        <span>{job.score || 0}/100</span>
      </div>
      <p className="job-meta">{job.company || "Unknown company"}</p>
      <p className="job-meta">{job.location || "Unknown location"}</p>
      <p className="job-fit">{job.fit_summary || "No summary provided."}</p>
      <a href={job.url} target="_blank" rel="noreferrer">Open listing</a>
    </article>
  );
}

function ReportPanel({ report, onEmailLatest, emailBusy, onShowEmailTooltip, onHideTooltip }) {
  if (!report) return <p className="assistant-text">No report selected.</p>;
  const [remainingOpen, setRemainingOpen] = useState(false);

  const topJobs = report.top_jobs || [];
  const remainingJobs = report.remaining_jobs || [];
  const title = report.report_name || report.report_path?.split("/").pop() || "Untitled";

  return (
    <section className="report-panel">
      <div className="report-panel-header">
        <h3>{`Report - ${title}`}</h3>
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
  if (normalized.includes("fetch")) return "Fetching Jobs";
  if (normalized.includes("description")) return "Getting Descriptions";
  if (normalized.includes("score")) return "Scoring Jobs";
  if (normalized.includes("report")) return "Creating Report";
  const fallbackWords = [
    "Searching",
    "Working",
    "Hunting",
    "Seeking",
    "Inquiring",
    "Rummaging",
  ];
  const seed = normalized.split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return `${fallbackWords[seed % fallbackWords.length]}...`;
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
  const [introMode, setIntroMode] = useState(true);
  const [introFadingOut, setIntroFadingOut] = useState(false);
  const [returningToIntro, setReturningToIntro] = useState(false);
  const [hasResume, setHasResume] = useState(false);
  const [resumeUploads, setResumeUploads] = useState([]);
  const [resumePickerOpen, setResumePickerOpen] = useState(false);
  const [resumePlusClosing, setResumePlusClosing] = useState(false);
  const [floatingTooltip, setFloatingTooltip] = useState({ visible: false, text: "", top: 0, left: 0, placement: "left" });
  const [pulsingResumeName, setPulsingResumeName] = useState("");

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
  const chatAbortRef = useRef(null);
  const stopRequestedRef = useRef(false);
  const runIdRef = useRef("");
  const bottomTextareaHeightRef = useRef(0);

  useEffect(() => {
    runIdRef.current = runId;
  }, [runId]);

  function appendText(text, role = "assistant", focusBlock = null) {
    const newId = crypto.randomUUID();
    setMessages((previous) => [...previous, { id: newId, role, type: "text", text }]);
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

    if (introMode) {
      setIntroFadingOut(true);
      setTimeout(() => {
        setIntroMode(false);
        setIntroFadingOut(false);
      }, 280);
    }

    appendText(trimmed, "user", "start");
    setQuery("");
    requestAnimationFrame(() => {
      resizeBottomComposerTextarea();
    });
    setBusy(true);
    setRunState({ status: "running", step: "Fetching jobs", progress: 0 });

    try {
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
      appendText(statusText);
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

        <div className="report-list">
          {!sidebarCollapsed && <h3 className="report-list-title">Reports</h3>}
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
          >
            <FontAwesomeIcon icon={faCircleUser} className="profile-icon" />
            <span className={`profile-text ${sidebarCollapsed ? "hidden" : ""}`}>Profile</span>
          </button>
        </div>
      </aside>

      <section className="chat-layout" onClick={() => setOpenReportMenu("")}>
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
                <div className={message.role === "user" ? "user-bubble" : "assistant-text"}>{message.text}</div>
              )}
            </div>
          ))}

          {runState?.status === "running" && (
            <div className="chat-message assistant">
              <div className="assistant-text status-shimmer">{formatSearchStep(runState.step)}</div>
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
        </div>
      </section>
    </main>
  );
}
