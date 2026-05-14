import React from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertCircle,
  Archive,
  CheckCircle,
  ChevronRight,
  Database,
  ExternalLink,
  FileText,
  History,
  Image as ImageIcon,
  LayoutDashboard,
  Loader2,
  Mail,
  Moon,
  RefreshCw,
  Save,
  Send,
  Sun,
  Table2,
  Terminal,
  Upload,
  UserCheck
} from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';
const ENGINE_LABEL = 'best.pt + VietOCR';

const initialLogs = [
  { time: new Date().toLocaleTimeString(), msg: 'He thong da san sang. Cho tep dau vao...', type: 'info' }
];

function fieldLabel(key) {
  return key.replace(/_/g, ' ');
}

function shipmentImageUrl(shipment) {
  return shipment?.id ? `${API_BASE}/api/shipments/${shipment.id}/image?v=${encodeURIComponent(shipment.updatedAt || shipment.createdAt || '')}` : null;
}

function App() {
  const [isDark, setIsDark] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState('dashboard');
  const [localPreview, setLocalPreview] = React.useState(null);
  const [serverPreview, setServerPreview] = React.useState(null);
  const [isProcessing, setIsProcessing] = React.useState(false);
  const [logs, setLogs] = React.useState(initialLogs);
  const [results, setResults] = React.useState(null);
  const [currentShipment, setCurrentShipment] = React.useState(null);
  const [reviewTasks, setReviewTasks] = React.useState([]);
  const [sheetRows, setSheetRows] = React.useState([]);
  const [appConfig, setAppConfig] = React.useState(null);
  const [selectedTask, setSelectedTask] = React.useState(null);
  const [editBuffer, setEditBuffer] = React.useState(null);
  const [exportingId, setExportingId] = React.useState(null);
  const [storingId, setStoringId] = React.useState(null);
  const logEndRef = React.useRef(null);

  React.useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  React.useEffect(() => {
    loadReviewQueue();
    loadSheetRows();
    loadAppConfig();
  }, []);

  const theme = isDark ? 'app dark' : 'app light';
  const visibleResults = results ? Object.entries(results).slice(0, 11) : [];
  const previewSrc = serverPreview || localPreview;

  function addLog(msg, type = 'info') {
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), msg, type }]);
  }

  async function loadReviewQueue() {
    try {
      const response = await fetch(`${API_BASE}/api/shipments/review`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setReviewTasks(await response.json());
    } catch {
      setReviewTasks([]);
    }
  }

  async function loadSheetRows() {
    try {
      const response = await fetch(`${API_BASE}/api/shipments`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setSheetRows(await response.json());
    } catch {
      setSheetRows([]);
    }
  }

  async function loadAppConfig() {
    try {
      const response = await fetch(`${API_BASE}/api/app/config`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setAppConfig(await response.json());
    } catch {
      setAppConfig(null);
    }
  }

  async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    setLocalPreview(file.type.startsWith('image/') ? URL.createObjectURL(file) : null);
    setServerPreview(null);
    setIsProcessing(true);
    setResults(null);
    setCurrentShipment(null);
    addLog(`Upload ${file.name}. Chay ${ENGINE_LABEL}...`, 'info');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ocrBackend', 'vietocr');

    try {
      const response = await fetch(`${API_BASE}/api/shipments/extract`, {
        method: 'POST',
        body: formData
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);

      setResults(payload.shipment.fields);
      setCurrentShipment(payload.shipment);
      setServerPreview(shipmentImageUrl(payload.shipment));
      addLog('Trich xuat du lieu hoan tat, da tao preview JPG.', 'success');
      if (payload.shipment.needReview) {
        addLog('Thieu truong bat buoc hoac do tin cay thap. Da dua vao Human Review.', 'error');
      }
      await Promise.all([loadReviewQueue(), loadSheetRows()]);
    } catch (error) {
      addLog(`Loi xu ly: ${error.message}`, 'error');
    } finally {
      setIsProcessing(false);
      event.target.value = '';
    }
  }

  function selectTask(task) {
    setSelectedTask(task);
    setEditBuffer({ ...(task.fields || {}) });
  }

  async function submitReview() {
    if (!selectedTask || !editBuffer) return;
    addLog(`Dang luu chinh sua cho task ${selectedTask.id}...`, 'info');
    try {
      const response = await fetch(`${API_BASE}/api/shipments/${selectedTask.id}/review`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields: editBuffer, reviewedBy: 'operator' })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
      addLog(`Task ${selectedTask.id} da xac nhan va luu vao MongoDB.`, 'success');
      setSelectedTask(null);
      setEditBuffer(null);
      await Promise.all([loadReviewQueue(), loadSheetRows()]);
    } catch (error) {
      addLog(`Khong luu duoc review: ${error.message}`, 'error');
    }
  }

  async function exportShipment(shipment, mode) {
    setExportingId(`${shipment.id}-${mode}`);
    const body = {
      sheet: mode === 'sheet' || mode === 'both',
      email: mode === 'email' || mode === 'both'
    };
    try {
      const response = await fetch(`${API_BASE}/api/shipments/${shipment.id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
      addLog(`Export ${mode} thanh cong cho ${shipment.fields?.ma_van_don || shipment.id}.`, 'success');
    } catch (error) {
      addLog(`Export that bai: ${error.message}`, 'error');
    } finally {
      setExportingId(null);
    }
  }

  async function storeShipment(shipment) {
    setStoringId(shipment.id);
    try {
      const response = await fetch(`${API_BASE}/api/shipments/${shipment.id}/storage`, {
        method: 'POST'
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
      addLog(`Da luu ${payload.imageName} vao storage.json (${payload.savedVersions} ban).`, 'success');
      await loadAppConfig();
    } catch (error) {
      addLog(`Luu storage.json that bai: ${error.message}`, 'error');
    } finally {
      setStoringId(null);
    }
  }

  return (
    <div className={theme}>
      <aside className="sidebar">
        <div className="brand">
          <Database size={22} />
          <span>Mail Detection</span>
        </div>

        <nav className="nav">
          <button className={activeTab === 'dashboard' ? 'active' : ''} onClick={() => setActiveTab('dashboard')}>
            <LayoutDashboard size={19} />
            <span>Dashboard</span>
          </button>
          <button className={activeTab === 'review' ? 'active' : ''} onClick={() => setActiveTab('review')}>
            <UserCheck size={19} />
            <span>Human Review</span>
            {reviewTasks.length > 0 && <b>{reviewTasks.length}</b>}
          </button>
          <button className={activeTab === 'sheet' ? 'active' : ''} onClick={() => { setActiveTab('sheet'); loadSheetRows(); }}>
            <Table2 size={19} />
            <span>GG Sheet</span>
          </button>
        </nav>

        <div className="model-box">
          <div className="model-title">
            <History size={14} />
            <span>Active Engine</span>
          </div>
          <strong className="engine-name">{ENGINE_LABEL}</strong>
          <div className="progress"><i /></div>
          <div className="model-meta">
            <span>Local runtime</span>
            <strong>READY</strong>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <h1>{activeTab === 'dashboard' ? 'AI Extraction Pipeline' : activeTab === 'review' ? 'Human-in-the-loop Review' : 'GG Sheet Export'}</h1>
          <div className="top-actions">
            <span className="engine-pill">{ENGINE_LABEL}</span>
            <button className="icon-btn" onClick={() => setIsDark(!isDark)} aria-label="Toggle theme">
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <span className="live"><i />Live Engine</span>
          </div>
        </header>

        <main className="content">
          {activeTab === 'dashboard' && (
            <div className="dashboard-grid">
              <section className="left-stack">
                <label className="dropzone">
                  <input type="file" onChange={handleFileUpload} accept="image/*,.heic,.heif" />
                  <span className="upload-icon"><Upload size={42} /></span>
                  <strong>Tai anh buu kien len he thong</strong>
                  <small>YOLOv8 best.pt + VietOCR + MongoDB</small>
                </label>

                <div className="panel preview-panel">
                  <div className="panel-head">
                    <span><ImageIcon size={16} />Detection Preview</span>
                    {isProcessing && <Loader2 className="spin" size={17} />}
                  </div>
                  <ImagePreview src={previewSrc} loading={isProcessing} />
                </div>
              </section>

              <section className="right-stack">
                <div className="panel result-panel">
                  <div className="result-head">
                    <h2>Extraction Results</h2>
                    {currentShipment?.needReview ? (
                      <span className="pill warn"><AlertCircle size={13} />Need Review</span>
                    ) : results ? (
                      <span className="pill ok"><CheckCircle size={13} />Ready</span>
                    ) : null}
                  </div>

                  {!results ? (
                    <div className="empty">Pending extraction...</div>
                  ) : (
                    <>
                      <div className="fields">
                        {visibleResults.map(([key, value]) => (
                          <div className="field" key={key}>
                            <span>{fieldLabel(key)}</span>
                            <strong>{String(value || '---')}</strong>
                          </div>
                        ))}
                      </div>
                      <div className="button-row">
                        <button className="primary-action" onClick={() => setActiveTab('review')}>
                          <UserCheck size={15} />
                          Open Review
                        </button>
                        <button className="primary-action alt" onClick={() => { setActiveTab('sheet'); loadSheetRows(); }}>
                          <Table2 size={15} />
                          GG Sheet
                        </button>
                      </div>
                    </>
                  )}
                </div>

                <Console logs={logs} logEndRef={logEndRef} />
              </section>
            </div>
          )}

          {activeTab === 'review' && (
            <div className="review-grid">
              <section className="panel queue">
                <div className="panel-head"><span>Pending Queue ({reviewTasks.length})</span></div>
                {reviewTasks.map(task => (
                  <button
                    key={task.id}
                    className={selectedTask?.id === task.id ? 'task active-task' : 'task'}
                    onClick={() => selectTask(task)}
                  >
                    <img className="task-img" src={shipmentImageUrl(task)} alt="" />
                    <span>
                      <strong>{task.fields?.ma_van_don || task.id}</strong>
                      <small>{task.fields?.nguoi_gui || 'Unknown'} {'->'} {task.fields?.nguoi_nhan || 'Unknown'}</small>
                    </span>
                    <ChevronRight size={17} />
                  </button>
                ))}
                {reviewTasks.length === 0 && <div className="empty queue-empty">Khong co task can duyet.</div>}
              </section>

              <section className="review-detail">
                {!selectedTask ? (
                  <div className="review-empty">
                    <UserCheck size={64} />
                    <strong>Chon mot task de review</strong>
                  </div>
                ) : (
                  <>
                    <div className="review-image">
                      <img src={shipmentImageUrl(selectedTask)} alt={selectedTask.originalFilename || 'Review'} />
                    </div>
                    <div className="panel editor">
                      <div className="editor-head">
                        <h2><FileText size={19} />Correction Editor</h2>
                        <span className="pill warn">LOW CONFIDENCE</span>
                      </div>
                      <div className="edit-fields">
                        {Object.keys(editBuffer || {}).map(key => (
                          <label key={key}>
                            <span>{fieldLabel(key)}</span>
                            <input
                              value={editBuffer[key] ?? ''}
                              onChange={e => setEditBuffer({ ...editBuffer, [key]: e.target.value })}
                            />
                          </label>
                        ))}
                      </div>
                      <div className="editor-actions">
                        <button className="save" onClick={submitReview}>
                          <Save size={18} />
                          Submit & Save
                        </button>
                        <button className="secondary" onClick={() => setSelectedTask(null)}>Discard</button>
                      </div>
                    </div>
                  </>
                )}
              </section>
            </div>
          )}

          {activeTab === 'sheet' && (
            <div className="sheet-page">
              <div className="sheet-toolbar">
                <div>
                  <h2>GG Sheet</h2>
                  <p>{sheetRows.length} ban ghi trong MongoDB. Storage file: {appConfig?.storagePath || 'storage.json'}</p>
                </div>
                <div className="toolbar-actions">
                  <a
                    className={appConfig?.googleSheetUrl ? 'secondary link-button' : 'secondary link-button disabled'}
                    href={appConfig?.googleSheetUrl || undefined}
                    target="_blank"
                    rel="noreferrer"
                    aria-disabled={!appConfig?.googleSheetUrl}
                  >
                    <ExternalLink size={16} />
                    Open Google Sheet
                  </a>
                  <button className="secondary" onClick={() => { loadSheetRows(); loadAppConfig(); }}>
                    <RefreshCw size={16} />
                    Refresh
                  </button>
                </div>
              </div>

              <div className="panel sheet-table">
                {sheetRows.map(row => (
                  <div className="sheet-row" key={row.id}>
                    <img src={shipmentImageUrl(row)} alt="" />
                    <div className="sheet-main">
                      <strong>{row.fields?.ma_van_don || '---'}</strong>
                      <span>{row.fields?.nguoi_gui || '---'} {'->'} {row.fields?.nguoi_nhan || '---'}</span>
                      <small>{row.status} | {new Date(row.createdAt).toLocaleString()}</small>
                    </div>
                    <div className="sheet-actions">
                      <button onClick={() => exportShipment(row, 'sheet')} disabled={!!exportingId}>
                        {exportingId === `${row.id}-sheet` ? <Loader2 className="spin" size={15} /> : <Table2 size={15} />}
                        Sheet
                      </button>
                      <button onClick={() => exportShipment(row, 'email')} disabled={!!exportingId}>
                        {exportingId === `${row.id}-email` ? <Loader2 className="spin" size={15} /> : <Mail size={15} />}
                        Email
                      </button>
                      <button onClick={() => exportShipment(row, 'both')} disabled={!!exportingId}>
                        {exportingId === `${row.id}-both` ? <Loader2 className="spin" size={15} /> : <Send size={15} />}
                        Both
                      </button>
                      <button onClick={() => storeShipment(row)} disabled={!!storingId}>
                        {storingId === row.id ? <Loader2 className="spin" size={15} /> : <Archive size={15} />}
                        Storage
                      </button>
                    </div>
                  </div>
                ))}
                {sheetRows.length === 0 && <div className="empty">Chua co ban ghi.</div>}
              </div>
            </div>
          )}
        </main>
      </section>
    </div>
  );
}

function ImagePreview({ src, loading }) {
  return (
    <div className="preview">
      {src ? (
        <div className="image-wrap real-preview">
          <img src={src} alt="Detection preview" />
        </div>
      ) : (
        <p>{loading ? 'Processing image...' : 'No active signal'}</p>
      )}
    </div>
  );
}

function Console({ logs, logEndRef }) {
  return (
    <div className="console">
      <div className="console-head"><Terminal size={14} />System Console</div>
      <div className="console-body">
        {logs.map((log, index) => (
          <div className="log" key={`${log.time}-${index}`}>
            <time>{log.time}</time>
            <span className={log.type}>{log.msg}</span>
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
