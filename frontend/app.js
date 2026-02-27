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

document.getElementById('diary-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const entryType = document.getElementById('entry-type').value;
    const text = document.getElementById('diary-text').value;
    const audioData = audioChunks.length > 0 ? await getAudioBase64() : null;
    
    if (!text && !audioData) {
        showNotification('Please enter text or record audio', 'error');
        return;
    }
    
    showLoading(true);
    
    try {
        const formData = new FormData();
        if (text) formData.append('text', text);
        if (audioData) formData.append('audio_data', audioData);
        formData.append('entry_type', entryType);
        formData.append('timestamp', new Date().toISOString());
        
        const response = await fetch(`${API_BASE_URL}/api/diary/entry`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create entry');
        }
        
        const entry = await response.json();
        showNotification('Entry created successfully!', 'success');
        
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

async function loadDiaryEntries() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/diary/entries`);
        const entries = await response.json();
        
        const entriesList = document.getElementById('entries-list');
        if (entries.length === 0) {
            entriesList.innerHTML = '<div class="placeholder-text">No entries yet. Create your first entry above!</div>';
            return;
        }
        
        entriesList.innerHTML = entries.map(entry => `
            <div class="entry-card">
                <div class="entry-header">
                    <span class="entry-type badge badge-${entry.entry_type}">${entry.entry_type}</span>
                    <span class="entry-date">${new Date(entry.timestamp).toLocaleString()}</span>
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
        `).join('');
    } catch (error) {
        console.error('Error loading entries:', error);
    }
}

async function loadDiarySummary() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/diary/summary`);
        const summary = await response.json();
        
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
                    <div class="stat-value">${summary.common_symptoms.length}</div>
                    <div class="stat-label">Tracked Symptoms</div>
                </div>
            </div>
        `;
        document.getElementById('summary-stats').innerHTML = statsHtml;
        
        const chartsHtml = `
            <div id="sentiment-chart" style="margin: 20px 0;"></div>
            <div id="symptoms-chart" style="margin: 20px 0;"></div>
        `;
        document.getElementById('summary-charts').innerHTML = chartsHtml;
        
        if (summary.sentiment_trend && summary.sentiment_trend.length > 0) {
            const sentimentData = summary.sentiment_trend.map(s => ({
                x: [s.sentiment],
                y: [s.count],
                type: 'bar',
                name: s.sentiment,
                marker: { color: s.sentiment === 'positive' ? 'green' : s.sentiment === 'negative' ? 'red' : 'gray' }
            }));
            
            Plotly.newPlot('sentiment-chart', sentimentData, {
                title: 'Sentiment Distribution',
                xaxis: { title: 'Sentiment' },
                yaxis: { title: 'Count' }
            });
        }
        
        if (summary.common_symptoms && summary.common_symptoms.length > 0) {
            const symptomsData = [{
                x: summary.common_symptoms.map(s => s.symptom),
                y: summary.common_symptoms.map(s => s.count),
                type: 'bar',
                marker: { color: 'steelblue' }
            }];
            
            Plotly.newPlot('symptoms-chart', symptomsData, {
                title: 'Common Symptoms',
                xaxis: { title: 'Symptom' },
                yaxis: { title: 'Frequency' }
            });
        }
        
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

async function deleteEntry(entryId) {
    if (!confirm('Are you sure you want to delete this entry?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/diary/entries/${entryId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('Entry deleted', 'success');
            loadDiaryEntries();
            loadDiarySummary();
        }
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
        showNotification('Please enter text or record audio', 'error');
        return;
    }
    
    showLoading(true);
    
    try {
        const formData = new FormData();
        if (audioData) {
            formData.append('audio_data', audioData);
            formData.append('language', 'en-US');
        } else {
            formData.append('text', text);
        }
        
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
