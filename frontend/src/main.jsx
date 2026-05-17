import React from 'react';
import { createRoot } from 'react-dom/client';
import {
  AlertCircle,
  Archive,
  BrainCircuit,
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
  Trash2,
  Upload,
  UserCheck
} from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

const BACKEND_OPTIONS = [
  { value: 'vietocr',   label: 'VietOCR (fine-tuned)' },
  { value: 'easyocr',   label: 'EasyOCR' },
  { value: 'paddleocr', label: 'PaddleOCR (PP-OCRv3)' },
];

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
  const [selectedBackend, setSelectedBackend] = React.useState('vietocr');
  const [localPreview, setLocalPreview] = React.useState(null);
  const [serverPreview, setServerPreview] = React.useState(null);
  const [isProcessing, setIsProcessing] = React.useState(false);
  const [logs, setLogs] = React.useState(initialLogs);
  const [results, setResults] = React.useState(null);
  const [currentShipment, setCurrentShipment] = React.useState(null);
  const [reviewTasks, setReviewTasks] = React.useState([]);
  const [sheetRows, setSheetRows] = React.useState([]);
  const [appConfig, setAppConfig] = React.useState(null);
  const [trainingTab, setTrainingTab] = React.useState('confirm');
  const [trainingStatus, setTrainingStatus] = React.useState(null);
  const [storageCatalog, setStorageCatalog] = React.useState(null);
  const [trainingBusy, setTrainingBusy] = React.useState(false);
  const [selectedTask, setSelectedTask] = React.useState(null);
  const [editBuffer, setEditBuffer] = React.useState(null);
  const [reviewSubmitting, setReviewSubmitting] = React.useState(false);
  const [exportingId, setExportingId] = React.useState(null);
  const [storingId, setStoringId] = React.useState(null);
  const [exportingAll, setExportingAll] = React.useState(false);
  const [storedVersions, setStoredVersions] = React.useState({});
  const logEndRef = React.useRef(null);

  React.useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  React.useEffect(() => {
    loadReviewQueue();
    loadSheetRows();
    loadAppConfig();
    loadTrainingData();
  }, []);

  const theme = isDark ? 'app dark' : 'app light';
  const visibleResults = results ? Object.entries(results).slice(0, 11) : [];
  const previewSrc = serverPreview || localPreview;
  const engineLabel = `best.pt + ${BACKEND_OPTIONS.find(o => o.value === selectedBackend)?.label ?? selectedBackend}`;

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

  async function loadTrainingData() {
    try {
      const [statusResponse, storageResponse] = await Promise.all([
        fetch(`${API_BASE}/api/app/training/status`),
        fetch(`${API_BASE}/api/app/storage`)
      ]);
      if (!statusResponse.ok) throw new Error(`Training HTTP ${statusResponse.status}`);
      if (!storageResponse.ok) throw new Error(`Storage HTTP ${storageResponse.status}`);
      setTrainingStatus(await statusResponse.json());
      setStorageCatalog(await storageResponse.json());
    } catch {
      setTrainingStatus(null);
      setStorageCatalog(null);
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
    addLog(`Upload ${file.name}. Chay ${engineLabel}...`, 'info');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ocrBackend', selectedBackend);

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
      } else {
        await saveShipmentToSheet(payload.shipment);
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
    if (!selectedTask || !editBuffer || reviewSubmitting) return;
    setReviewSubmitting(true);
    addLog(`Dang luu chinh sua cho task ${selectedTask.id}...`, 'info');
    try {
      const response = await fetch(`${API_BASE}/api/shipments/${selectedTask.id}/review`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields: editBuffer, reviewedBy: 'operator' })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
      addLog(`Task ${selectedTask.id} da xac nhan, luu MongoDB va them vao storage.json.`, 'success');
      await saveShipmentToSheet(payload);
      setSelectedTask(null);
      setEditBuffer(null);
      await Promise.all([loadReviewQueue(), loadSheetRows(), loadTrainingData()]);
    } catch (error) {
      addLog(`Khong luu duoc review: ${error.message}`, 'error');
    } finally {
      setReviewSubmitting(false);
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

  async function saveShipmentToSheet(shipment) {
    try {
      const response = await fetch(`${API_BASE}/api/shipments/${shipment.id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sheet: true, email: false })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
      addLog(`Da luu Sheet cho ${shipment.fields?.ma_van_don || shipment.id}.`, 'success');
    } catch (error) {
      addLog(`Luu Sheet that bai: ${error.message}`, 'error');
    }
  }

  async function exportAllShipments() {
    setExportingAll(true);
    try {
      const response = await fetch(`${API_BASE}/api/shipments/export-all`, {
        method: 'POST'
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
      addLog(`Da luu ${payload.exported} ban ghi vao Google Sheet. Bo qua ${payload.skipped} ban ghi thieu ma van don.`, 'success');
      await loadSheetRows();
    } catch (error) {
      addLog(`Luu tat ca vao Sheet that bai: ${error.message}`, 'error');
    } finally {
      setExportingAll(false);
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
      setStoredVersions(prev => ({ ...prev, [shipment.id]: payload.savedVersions }));
      addLog(`Da luu ${payload.imageName} vao storage.json (${payload.savedVersions} ban).`, 'success');
      await Promise.all([loadAppConfig(), loadTrainingData(), loadSheetRows()]);
      setTrainingTab('storage');
      setActiveTab('training');
    } catch (error) {
      addLog(`Luu storage.json that bai: ${error.message}`, 'error');
    } finally {
      setStoringId(null);
    }
  }

  async function confirmTraining() {
    setTrainingBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/app/training/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || `HTTP ${response.status}`);
      addLog(`Training request ${payload.requestId} da duoc tao.`, 'success');
      await loadTrainingData();
    } catch (error) {
      addLog(`Khong the bat dau training: ${error.message}`, 'error');
    } finally {
      setTrainingBusy(false);
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
          <button className={activeTab === 'training' ? 'active' : ''} onClick={() => { setActiveTab('training'); loadTrainingData(); }}>
            <BrainCircuit size={19} />
            <span>Training</span>
          </button>
        </nav>

        <div className="model-box">
          <div className="model-title">
            <History size={14} />
            <span>Active Engine</span>
          </div>
          <strong className="engine-name">{engineLabel}</strong>
          <div className="progress"><i /></div>
          <div className="model-meta">
            <span>Local runtime</span>
            <strong>READY</strong>
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <h1>{activeTab === 'dashboard' ? 'AI Extraction Pipeline' : activeTab === 'review' ? 'Human-in-the-loop Review' : activeTab === 'sheet' ? 'GG Sheet Export' : 'Training Control'}</h1>
          <div className="top-actions">
            <span className="engine-pill">{engineLabel}</span>
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
                <div className="model-select-row">
                  <label htmlFor="ocr-backend-select">OCR Model</label>
                  <select
                    id="ocr-backend-select"
                    value={selectedBackend}
                    onChange={e => setSelectedBackend(e.target.value)}
                    disabled={isProcessing}
                  >
                    {BACKEND_OPTIONS.map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>

                <label className="dropzone">
                  <input type="file" onChange={handleFileUpload} accept="image/*,.heic,.heif" disabled={isProcessing} />
                  <span className="upload-icon"><Upload size={42} /></span>
                  <strong>Tai anh buu kien len he thong</strong>
                  <small>YOLOv8 best.pt + {BACKEND_OPTIONS.find(o => o.value === selectedBackend)?.label} + MongoDB</small>
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
                        <button className="save" onClick={submitReview} disabled={reviewSubmitting}>
                          {reviewSubmitting ? <Loader2 className="spin" size={18} /> : <Save size={18} />}
                          {reviewSubmitting ? 'Saving...' : 'Submit & Save'}
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
                  <button className="secondary" onClick={exportAllShipments} disabled={exportingAll}>
                    {exportingAll ? <Loader2 className="spin" size={16} /> : <Table2 size={16} />}
                    Save All
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
                        {storedVersions[row.id] ? `Stored ${storedVersions[row.id]}` : 'Save & View'}
                      </button>
                    </div>
                  </div>
                ))}
                {sheetRows.length === 0 && <div className="empty">Chua co ban ghi.</div>}
              </div>
            </div>
          )}

          {activeTab === 'training' && (
            <div className="training-page">
              <div className="training-tabs">
                <button className={trainingTab === 'confirm' ? 'active' : ''} onClick={() => setTrainingTab('confirm')}>
                  <BrainCircuit size={16} />
                  Confirm Training
                </button>
                <button className={trainingTab === 'storage' ? 'active' : ''} onClick={() => setTrainingTab('storage')}>
                  <Archive size={16} />
                  Storage Review
                </button>
                <button className="secondary small-refresh" onClick={loadTrainingData}>
                  <RefreshCw size={15} />
                  Refresh
                </button>
              </div>

              {trainingTab === 'confirm' && (
                <div className="training-grid">
                  <section className="panel training-card">
                    <div className="training-metric">
                      <span>Reviewed snapshots</span>
                      <strong>{trainingStatus?.reviewCount ?? 0}</strong>
                      <small>Minimum required: {trainingStatus?.minimumReviews ?? 20}</small>
                    </div>
                    <div className="training-progress">
                      <i style={{ width: `${Math.min(100, ((trainingStatus?.reviewCount || 0) / (trainingStatus?.minimumReviews || 20)) * 100)}%` }} />
                    </div>
                    <div className={trainingStatus?.canTrain ? 'training-state ready' : 'training-state blocked'}>
                      {trainingStatus?.canTrain ? 'Ready for training' : `Need ${trainingStatus?.missingReviews ?? 20} more reviewed snapshots`}
                    </div>
                  </section>

                  <section className="panel training-warning">
                    <h2><Trash2 size={18} />Training confirmation</h2>
                    <p>{trainingStatus?.reason || 'Training requires at least 20 reviewed storage snapshots.'}</p>
                    <div className="warning-box">
                      Sau khi xac nhan training, flow training se dung data review moi. Khi train xong, model cu se bi thay the va app se ap dung model moi ngay.
                    </div>
                    <div className="model-path">
                      <span>Active model</span>
                      <code>{trainingStatus?.activeModelPath || 'models/yolo_regions/mail_3field/weights/best.pt'}</code>
                    </div>
                    <button
                      className="danger-action"
                      onClick={confirmTraining}
                      disabled={!trainingStatus?.canTrain || trainingBusy}
                    >
                      {trainingBusy ? <Loader2 className="spin" size={16} /> : <BrainCircuit size={16} />}
                      Confirm & Start Training
                    </button>
                  </section>
                </div>
              )}

              {trainingTab === 'storage' && (
                <div className="storage-review">
                  <div className="sheet-toolbar">
                    <div>
                      <h2>Storage Review</h2>
                      <p>{storageCatalog?.imageCount || 0} anh, {storageCatalog?.totalReviews || 0} review snapshots trong storage.json.</p>
                    </div>
                    <span className="engine-pill">{storageCatalog?.storagePath || 'storage.json'}</span>
                  </div>

                  <div className="storage-grid">
                    {(storageCatalog?.images || []).map(item => (
                      <article className="storage-card panel" key={item.imageName}>
                        {item.shipmentId ? (
                          <img src={`${API_BASE}/api/shipments/${item.shipmentId}/image`} alt={item.imageName} />
                        ) : (
                          <div className="storage-no-image"><FileText size={36} /></div>
                        )}
                        <div className="storage-body">
                          <div className="storage-title">
                            <strong>{item.imageName}</strong>
                            <span>{item.versions} saved</span>
                          </div>
                          <div className="storage-fields">
                            {Object.entries(item.fields || {}).slice(0, 8).map(([key, value]) => (
                              <div key={key}>
                                <span>{fieldLabel(key)}</span>
                                <strong>{String(value || '---')}</strong>
                              </div>
                            ))}
                          </div>
                        </div>
                      </article>
                    ))}
                    {(storageCatalog?.images || []).length === 0 && <div className="empty panel">storage.json chua co du lieu review.</div>}
                  </div>
                </div>
              )}
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
