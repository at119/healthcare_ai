const API_BASE_URL = 'http://localhost:8000';

let mediaRecorder = null;
let audioChunks = [];
let currentRecordingType = null;

document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
        const tabName = button.dataset.tab;
        
        document.querySelectorAll('.tab-button').forEach(btn => btn.classList.remove('active'));
        button.classList.add('active');
        
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        document.getElementById(`${tabName}-tab`).classList.add('active');
    });
});

function saveEntriesToLocal(entries) {
    try {
        localStorage.setItem('diary_entries', JSON.stringify(entries));
    } catch (error) {
        console.error('Error saving to localStorage:', error);
        showNotification('Error saving entry to local storage', 'error');
    }
}

function loadEntriesFromLocal() {
    try {
        const stored = localStorage.getItem('diary_entries');
        return stored ? JSON.parse(stored) : [];
    } catch (error) {
        console.error('Error loading from localStorage:', error);
        return [];
    }
}

document.getElementById('diary-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const entryType = document.getElementById('entry-type').value;
    let text = document.getElementById('diary-text').value;
    const audioData = audioChunks.length > 0 ? await getAudioBase64() : null;
    
    if (!text && !audioData) {
        showNotification('Please enter text or record audio.', 'error');
        return;
    }
    
    showLoading(true);
    
    try {
        if (audioData && !text) {
            const formData = new FormData();
            formData.append('audio_data', audioData);
            formData.append('language', 'en-US');
            
            const response = await fetch(`${API_BASE_URL}/api/clinical/transcribe`, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to transcribe audio');
            }
            
            const result = await response.json();
            text = result.transcription;
        }
        
        const entry = {
            id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
            text: text,
            entry_type: entryType,
            timestamp: new Date().toISOString(),
            sentiment: analyzeSentiment(text),
            suggestions: []
        };
        
        const entries = loadEntriesFromLocal();
        entries.push(entry);
        saveEntriesToLocal(entries);
        
        showNotification('Entry saved!', 'success');
        
        document.getElementById('diary-text').value = '';
        audioChunks = [];
        document.getElementById('audio-playback').style.display = 'none';
        
        loadDiaryEntries();
        loadDiarySummary();
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    } finally {
        showLoading(false);
    }
});

let allEntries = [];

function analyzeSentiment(text) {
    const lowerText = text.toLowerCase();
    if (lowerText.match(/\b(good|great|excellent|happy|well|better|improved|feeling good)\b/)) {
        return 'positive';
    } else if (lowerText.match(/\b(bad|terrible|awful|sad|pain|hurt|worse|feeling bad|unwell)\b/)) {
        return 'negative';
    }
    return 'neutral';
}

function loadDiaryEntries() {
    allEntries = loadEntriesFromLocal();
    applyFilter();
}

function applyFilter() {
    const filterValue = document.getElementById('entry-filter').value;
    const entriesList = document.getElementById('entries-list');
    
    let filteredEntries = allEntries;
    if (filterValue !== 'all') {
        filteredEntries = allEntries.filter(entry => entry.entry_type === filterValue);
    }
    
    if (filteredEntries.length === 0) {
        entriesList.innerHTML = '<div class="placeholder-text">No entries found. Create your first entry above!</div>';
        return;
    }
    
    filteredEntries.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    entriesList.innerHTML = filteredEntries.map(entry => {
        const date = new Date(entry.timestamp);
        const dateStr = date.toLocaleDateString();
        const timeStr = date.toLocaleTimeString();
        
        return `
            <div class="entry-card">
                <div class="entry-header">
                    <span class="entry-type badge badge-${entry.entry_type}">${entry.entry_type}</span>
                    <span class="entry-date">${dateStr} at ${timeStr}</span>
                    <button class="btn-delete" onclick="deleteEntry('${entry.id}')">×</button>
                </div>
                <div class="entry-text">${entry.text}</div>
                ${entry.sentiment ? `<div class="entry-sentiment">Sentiment: <span class="sentiment-${entry.sentiment}">${entry.sentiment}</span></div>` : ''}
                ${entry.suggestions && entry.suggestions.length > 0 ? `
                    <div class="entry-suggestions">
                        <strong>Suggestions:</strong>
                        <ul>${entry.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

document.getElementById('entry-filter').addEventListener('change', applyFilter);

function loadDiarySummary() {
    try {
        const entries = loadEntriesFromLocal();
        
        if (entries.length === 0) {
            document.getElementById('summary-stats').innerHTML = '<div class="placeholder-text">No entries yet. Create entries to see your health summary.</div>';
            document.getElementById('summary-charts').innerHTML = '';
            document.getElementById('summary-suggestions').innerHTML = '';
            return;
        }
        
        const sentiments = entries.map(entry => entry.sentiment || analyzeSentiment(entry.text));
        const sentimentCounts = { positive: 0, negative: 0, neutral: 0 };
        sentiments.forEach(s => sentimentCounts[s] = (sentimentCounts[s] || 0) + 1);
        
        const diseases = {};
        const moods = {};
        const foods = {};
        const medications = {};
        
        entries.forEach(entry => {
            const text = entry.text.toLowerCase();
            
            if (entry.entry_type === 'disease') {
                const commonDiseases = ['diabetes', 'hypertension', 'asthma', 'arthritis', 'heart disease', 'cancer', 'thyroid', 'copd', 'depression', 'anxiety'];
                commonDiseases.forEach(disease => {
                    if (text.includes(disease)) {
                        diseases[disease] = (diseases[disease] || 0) + 1;
                    }
                });
            } else if (entry.entry_type === 'mood') {
                if (text.match(/\b(happy|good|great|excellent|positive)\b/)) {
                    moods['positive'] = (moods['positive'] || 0) + 1;
                } else if (text.match(/\b(sad|bad|terrible|negative|down)\b/)) {
                    moods['negative'] = (moods['negative'] || 0) + 1;
                } else {
                    moods['neutral'] = (moods['neutral'] || 0) + 1;
                }
            } else if (entry.entry_type === 'food') {
                const commonFoods = ['breakfast', 'lunch', 'dinner', 'snack', 'water', 'coffee', 'tea'];
                commonFoods.forEach(food => {
                    if (text.includes(food)) {
                        foods[food] = (foods[food] || 0) + 1;
                    }
                });
            } else if (entry.entry_type === 'medication') {
                const medWords = text.split(/\s+/).filter(w => w.length > 3);
                medWords.forEach(word => {
                    if (word.length > 0) {
                        medications[word] = (medications[word] || 0) + 1;
                    }
                });
            }
        });
        
        const dates = entries.map(e => new Date(e.timestamp)).filter(d => !isNaN(d.getTime()));
        const dateRange = dates.length > 0 ? {
            start: new Date(Math.min(...dates.map(d => d.getTime()))).toISOString(),
            end: new Date(Math.max(...dates.map(d => d.getTime()))).toISOString()
        } : { start: new Date().toISOString(), end: new Date().toISOString() };
        
        const summary = {
            total_entries: entries.length,
            date_range: dateRange,
            sentiment_trend: Object.entries(sentimentCounts).map(([sentiment, count]) => ({ sentiment, count })),
            common_diseases: Object.entries(diseases).map(([disease, count]) => ({ disease, count })).sort((a, b) => b.count - a.count).slice(0, 5),
            mood_patterns: Object.entries(moods).map(([mood, count]) => ({ mood, count })),
            suggestions: [],
            visualization_data: {
                time_series: entries.map(e => ({
                    date: e.timestamp,
                    sentiment: e.sentiment || analyzeSentiment(e.text),
                    type: e.entry_type
                })),
                sentiment_distribution: sentimentCounts
            }
        };
        
        const statsHtml = `
            <div class="summary-stats-grid">
                <div class="stat-card">
                    <div class="stat-value">${summary.total_entries}</div>
                    <div class="stat-label">Total Entries</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${summary.sentiment_trend.length}</div>
                    <div class="stat-label">Sentiment Categories</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${summary.common_diseases ? summary.common_diseases.length : 0}</div>
                    <div class="stat-label">Tracked Diseases</div>
                </div>
            </div>
        `;
        document.getElementById('summary-stats').innerHTML = statsHtml;
        
        document.getElementById('summary-charts').innerHTML = '';
        
        if (summary.suggestions && summary.suggestions.length > 0) {
            const suggestionsHtml = `
                <div class="suggestions-box">
                    <h3>AI Suggestions</h3>
                    <ul>${summary.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>
                </div>
            `;
            document.getElementById('summary-suggestions').innerHTML = suggestionsHtml;
        }
    } catch (error) {
        console.error('Error loading summary:', error);
    }
}

function deleteEntry(entryId) {
    if (!confirm('Are you sure you want to delete this entry?')) return;
    
    try {
        const entries = loadEntriesFromLocal();
        const filteredEntries = entries.filter(entry => entry.id !== entryId);
        saveEntriesToLocal(filteredEntries);
        
        showNotification('Entry deleted', 'success');
        loadDiaryEntries();
        loadDiarySummary();
    } catch (error) {
        showNotification(`Error deleting entry: ${error.message}`, 'error');
    }
}

document.getElementById('refresh-summary').addEventListener('click', () => {
    loadDiarySummary();
});

document.getElementById('clinical-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const text = document.getElementById('clinical-text').value;
    const audioData = audioChunks.length > 0 && currentRecordingType === 'clinical' ? await getAudioBase64() : null;
    
    if (!text && !audioData) {
        showNotification('Please enter text or record audio.', 'error');
        return;
    }
    
    showLoading(true);
    
    try {
        const diaryEntries = loadEntriesFromLocal();
        const relevantEntries = diaryEntries.filter(entry => 
            entry.entry_type === 'disease' || entry.entry_type === 'medication'
        );
        
        const formData = new FormData();
        if (audioData) {
            formData.append('audio_data', audioData);
            formData.append('language', 'en-US');
        } else {
            formData.append('text', text);
        }
        formData.append('diary_entries', JSON.stringify(relevantEntries));
        
        const endpoint = audioData 
            ? `${API_BASE_URL}/api/clinical/transcribe`
            : `${API_BASE_URL}/api/clinical/text-to-soap`;
        
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to process clinical note');
        }
        
        const result = await response.json();
        displayClinicalResults(result);
        showNotification('SOAP note generated successfully!', 'success');
        
        document.getElementById('clinical-text').value = '';
        audioChunks = [];
        document.getElementById('clinical-audio-playback').style.display = 'none';
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    } finally {
        showLoading(false);
    }
});

function displayClinicalResults(result) {
    const resultsDiv = document.getElementById('clinical-results');
    
    const html = `
        <div class="clinical-result">
            <div class="soap-section">
                <h3>Transcription</h3>
                <div class="transcription-box">${result.transcription}</div>
            </div>
            
            <div class="soap-section">
                <h3>SOAP Note</h3>
                <div class="soap-note">
                    <div class="soap-item">
                        <h4>Subjective (S)</h4>
                        <p>${result.soap_note.subjective}</p>
                    </div>
                    <div class="soap-item">
                        <h4>Objective (O)</h4>
                        <p>${result.soap_note.objective}</p>
                    </div>
                    <div class="soap-item">
                        <h4>Assessment (A)</h4>
                        <p>${result.soap_note.assessment}</p>
                    </div>
                    <div class="soap-item">
                        <h4>Plan (P)</h4>
                        <p>${result.soap_note.plan}</p>
                    </div>
                </div>
            </div>
            
            ${result.health_entities && result.health_entities.length > 0 ? `
                <div class="soap-section">
                    <h3>Extracted Health Entities</h3>
                    <div class="entities-list">
                        ${result.health_entities.map(entity => `
                            <div class="entity-item">
                                <strong>${entity.text}</strong> 
                                <span class="entity-category">${entity.category}</span>
                                <span class="entity-confidence">${(entity.confidence * 100).toFixed(1)}%</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            
        </div>
    `;
    
    resultsDiv.innerHTML = html;
}

document.getElementById('record-btn').addEventListener('click', startRecording.bind(null, 'diary'));
document.getElementById('stop-btn').addEventListener('click', stopRecording);

document.getElementById('clinical-record-btn').addEventListener('click', startRecording.bind(null, 'clinical'));
document.getElementById('clinical-stop-btn').addEventListener('click', stopRecording);

async function startRecording(type) {
    currentRecordingType = type;
    audioChunks = [];
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true
            }
        });
        
        let options = {};
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
            options = { mimeType: 'audio/webm;codecs=opus' };
        } else if (MediaRecorder.isTypeSupported('audio/webm')) {
            options = { mimeType: 'audio/webm' };
        }
        
        mediaRecorder = new MediaRecorder(stream, options);
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            const mimeType = mediaRecorder.mimeType || 'audio/webm';
            const audioBlob = new Blob(audioChunks, { type: mimeType });
            const audioUrl = URL.createObjectURL(audioBlob);
            
            const playbackId = type === 'diary' ? 'audio-playback' : 'clinical-audio-playback';
            const audioElement = document.getElementById(playbackId);
            audioElement.src = audioUrl;
            audioElement.style.display = 'block';
            
            stream.getTracks().forEach(track => track.stop());
        };
        
        mediaRecorder.start();
        
        const recordBtn = type === 'diary' ? document.getElementById('record-btn') : document.getElementById('clinical-record-btn');
        const stopBtn = type === 'diary' ? document.getElementById('stop-btn') : document.getElementById('clinical-stop-btn');
        const statusSpan = type === 'diary' ? document.getElementById('recording-status') : document.getElementById('clinical-recording-status');
        
        recordBtn.disabled = true;
        stopBtn.disabled = false;
        statusSpan.textContent = '🔴 Recording...';
    } catch (error) {
        showNotification('Error accessing microphone: ' + error.message, 'error');
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        
        const type = currentRecordingType;
        const recordBtn = type === 'diary' ? document.getElementById('record-btn') : document.getElementById('clinical-record-btn');
        const stopBtn = type === 'diary' ? document.getElementById('stop-btn') : document.getElementById('clinical-stop-btn');
        const statusSpan = type === 'diary' ? document.getElementById('recording-status') : document.getElementById('clinical-recording-status');
        
        recordBtn.disabled = false;
        stopBtn.disabled = true;
        statusSpan.textContent = '✓ Recording complete';
    }
}

async function getAudioBase64() {
    if (audioChunks.length === 0) return null;
    
    const mimeType = mediaRecorder ? mediaRecorder.mimeType : 'audio/webm';
    const audioBlob = new Blob(audioChunks, { type: mimeType });
    
    try {
        const wavBlob = await convertToWav(audioBlob);
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.readAsDataURL(wavBlob);
        });
    } catch (error) {
        console.error('Error converting audio:', error);
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.readAsDataURL(audioBlob);
        });
    }
}

async function convertToWav(audioBlob) {
    try {
        const arrayBuffer = await audioBlob.arrayBuffer();
        const audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000
        });
        
        console.log('Decoding audio data...');
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        console.log(`Audio decoded: ${audioBuffer.sampleRate}Hz, ${audioBuffer.numberOfChannels} channels, ${audioBuffer.length} samples`);
        
        const wav = audioBufferToWav(audioBuffer);
        console.log(`WAV created: ${wav.byteLength} bytes`);
        return new Blob([wav], { type: 'audio/wav' });
    } catch (error) {
        console.error('Error in convertToWav:', error);
        throw error;
    }
}

function audioBufferToWav(buffer) {
    const length = buffer.length;
    const numberOfChannels = buffer.numberOfChannels;
    const sampleRate = buffer.sampleRate;
    const bytesPerSample = 2;
    const blockAlign = numberOfChannels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;
    const dataSize = length * blockAlign;
    const bufferSize = 44 + dataSize;
    
    const arrayBuffer = new ArrayBuffer(bufferSize);
    const view = new DataView(arrayBuffer);
    
    const writeString = (offset, string) => {
        for (let i = 0; i < string.length; i++) {
            view.setUint8(offset + i, string.charCodeAt(i));
        }
    };
    
    writeString(0, 'RIFF');
    view.setUint32(4, bufferSize - 8, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numberOfChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, dataSize, true);
    
    let offset = 44;
    for (let i = 0; i < length; i++) {
        for (let channel = 0; channel < numberOfChannels; channel++) {
            const sample = Math.max(-1, Math.min(1, buffer.getChannelData(channel)[i]));
            view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
            offset += 2;
        }
    }
    
    return arrayBuffer;
}

function showLoading(show) {
    document.getElementById('loading-overlay').style.display = show ? 'flex' : 'none';
}

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification notification-${type} show`;
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

document.addEventListener('DOMContentLoaded', () => {
    loadDiaryEntries();
    loadDiarySummary();
});
