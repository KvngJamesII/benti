// Force unbuffered logging for Cloud Run
process.stdout.write = ((write) => {
  return (string, encoding, fd) => {
    write.call(process.stdout, string, encoding, fd);
  };
})(process.stdout.write);

console.log('\n🚀 [STARTUP] OTP King Bot process starting...\n');

const http = require('http');
const https = require('https');
const TelegramBot = require('node-telegram-bot-api');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

console.log('✅ [STARTUP] All modules loaded successfully\n');

// ==================== CONFIGURATION ====================
const CONFIG = {
  telegram_bot_token: '8171874869:AAE3B01g08v9fWoGGvwHBrvjggexhQe1cKE',
  telegram_chat_ids: [-1002826032710, -1003420206708],
  api_token: 'RlZVRklBUzSAYplnanhsQoRyhWaAdI5mfGyFf2aAlWiAj4BkYGGNSQ==',
  api_url: 'http://147.135.212.197/crapi/st/viewstats',
  poll_interval: 10000, // 10 seconds
  max_records: 10, // Maximum records to fetch per request
  user_name: 'OTP King',
  data_dir: './data-otp-king'
};

console.log('✅ [STARTUP] Configuration loaded\n');

// ==================== BOT CLASS ====================
class OTPKingBot {
  constructor() {
    console.log('🚀 [INIT] Initializing OTP King Bot...');
    this.telegramBot = null;
    this.sentMessageHashes = new Set();
    this.pollInterval = null;
    this.healthCheckInterval = null;
    this.isPolling = false;
    this.pollCount = 0;
    this.lastSuccessfulPoll = Date.now();
    this.otpsSentCount = 0;
    this.isRunning = false;
    this.messageHashFile = path.join(CONFIG.data_dir, 'sent-messages-otp-king.json');
    
    this.loadSentMessages();
  }

  log(level, message) {
    const timestamp = new Date().toISOString();
    const logLine = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
    console.log(logLine);
    process.stdout.write(''); // Force flush
  }

  loadSentMessages() {
    try {
      if (!fs.existsSync(CONFIG.data_dir)) {
        fs.mkdirSync(CONFIG.data_dir, { recursive: true });
        this.log('info', `📂 Created data directory: ${CONFIG.data_dir}`);
      }
      
      if (fs.existsSync(this.messageHashFile)) {
        const data = fs.readFileSync(this.messageHashFile, 'utf8');
        const hashes = JSON.parse(data);
        this.sentMessageHashes = new Set(hashes);
        this.log('info', `📂 Loaded ${this.sentMessageHashes.size} message hashes from file`);
      }
    } catch (err) {
      this.log('warn', `⚠️ Could not load messages: ${err.message}`);
    }
  }

  saveSentMessages() {
    try {
      if (!fs.existsSync(CONFIG.data_dir)) {
        fs.mkdirSync(CONFIG.data_dir, { recursive: true });
      }
      
      const hashArray = Array.from(this.sentMessageHashes).slice(-1000);
      fs.writeFileSync(this.messageHashFile, JSON.stringify(hashArray, null, 2));
      this.log('debug', `💾 Saved ${this.sentMessageHashes.size} message hashes`);
    } catch (err) {
      this.log('error', `Failed to save messages: ${err.message}`);
    }
  }

  getDateRangeParams() {
    const now = new Date();
    const dt2 = now.toISOString().replace('T', ' ').substring(0, 19);
    
    // Set dt1 to 2 hours ago
    const dt1_date = new Date(now.getTime() - (2 * 60 * 60 * 1000));
    const dt1 = dt1_date.toISOString().replace('T', ' ').substring(0, 19);
    
    return { dt1, dt2 };
  }

  async fetchLatestSMS() {
    try {
      this.log('debug', '📡 Fetching SMS from API...');

      // Build API URL with parameters
      const url = new URL(CONFIG.api_url);
      const dateRange = this.getDateRangeParams();
      
      url.searchParams.append('token', CONFIG.api_token);
      url.searchParams.append('dt1', dateRange.dt1);
      url.searchParams.append('dt2', dateRange.dt2);
      url.searchParams.append('records', CONFIG.max_records);

      const response = await this.makeHttpRequest(url.toString());

      // Handle array response format
      if (Array.isArray(response)) {
        this.lastSuccessfulPoll = Date.now();
        
        if (response.length === 0) {
          this.log('debug', '📭 No new messages from API');
          return [];
        }

        const messages = response.map((record) => {
          // Record format: [service_name, phone_number, message, datetime]
          const service = record[0] || 'Unknown';
          const phoneNumber = record[1] || 'Unknown';
          const messageText = record[2] || 'No content';
          const datetime = record[3] || '';
          
          // Create unique hash from the message data
          const msgData = `${datetime}_${phoneNumber}_${service}_${messageText}`;
          const hash = crypto.createHash('md5').update(msgData).digest('hex');
          
          return {
            hash,
            source_addr: service,
            destination_addr: phoneNumber,
            short_message: messageText,
            date: datetime,
            payout: '0'
          };
        });

        this.log('debug', `📬 Fetched ${messages.length} SMS messages from API`);
        return messages;

      } else {
        this.log('warn', '⚠️ Unexpected API response format');
        return [];
      }

    } catch (err) {
      this.log('error', `❌ SMS fetch error: ${err.message}`);
      return [];
    }
  }

  makeHttpRequest(url) {
    return new Promise((resolve, reject) => {
      const parsedUrl = new URL(url);
      const protocol = parsedUrl.protocol === 'https:' ? https : http;

      const options = {
        method: 'GET',
        timeout: 30000
      };

      const req = protocol.get(url, options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          try {
            const jsonData = JSON.parse(data);
            resolve(jsonData);
          } catch (err) {
            reject(new Error(`Failed to parse JSON: ${err.message}`));
          }
        });
      });

      req.on('error', (err) => {
        reject(err);
      });

      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Request timeout'));
      });
    });
  }

  async sendConnectionSuccessMessage() {
    try {
      const uptime = new Date().toISOString();
      const message = `
╔════════════════════════════════════╗
║     👑 OTP KING - CONNECTED 👑    ║
╚════════════════════════════════════╝

✅ <b>Status:</b> Connected
⏰ <b>Connected at:</b> ${uptime}
📡 <b>Active Channel:</b> ${CONFIG.telegram_chat_ids.length}
⏱️ <b>Poll Interval:</b> ${CONFIG.poll_interval / 1000}s
🔑 <b>API Token:</b> ${CONFIG.api_token.substring(0, 10)}...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    OTP Forwarding System
       Powered by IdleDeveloper
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
      `.trim();

      for (const chatId of CONFIG.telegram_chat_ids) {
        try {
          await this.telegramBot.sendMessage(chatId, message, { parse_mode: 'HTML' });
          this.log('info', `✅ Connection message sent to channel: ${chatId}`);
        } catch (err) {
          this.log('warn', `⚠️ Failed to send connection message to ${chatId}: ${err.message}`);
        }
      }
    } catch (err) {
      this.log('warn', `⚠️ Error sending connection message: ${err.message}`);
    }
  }

  async markExistingMessagesAsSent() {
    try {
      this.log('info', '🔄 Marking existing messages as sent...');
      const messages = await this.fetchLatestSMS();
      
      messages.forEach(sms => {
        this.sentMessageHashes.add(sms.hash);
      });
      
      this.saveSentMessages();
      this.log('info', `✅ Marked ${messages.length} existing messages as sent`);
    } catch (err) {
      this.log('warn', `⚠️ Error marking messages: ${err.message}`);
    }
  }

  maskPhoneNumber(phoneNumber) {
    if (!phoneNumber || phoneNumber.length < 4) {
      return phoneNumber;
    }
    
    const length = phoneNumber.length;
    const visibleStart = Math.ceil(length / 3);
    const visibleEnd = Math.ceil(length / 3);
    
    const start = phoneNumber.substring(0, visibleStart);
    const end = phoneNumber.substring(length - visibleEnd);
    
    return `${start}${'*'.repeat(length - visibleStart - visibleEnd)}${end}`;
  }

  extractOTP(message) {
    if (!message) return null;
    
    const patterns = [
      /\d{3}-\d{3}/g,
      /code[:\s]+(\d{3,8})/gi,
      /otp[:\s]+(\d{3,8})/gi,
      /verification[:\s]+(\d{3,8})/gi,
      /pin[:\s]+(\d{3,8})/gi,
      /\b(\d{4,8})\b/g,
    ];
    
    for (const pattern of patterns) {
      const matches = message.match(pattern);
      if (matches && matches.length > 0) {
        let otp = matches[0];
        otp = otp.replace(/code[:\s]+/gi, '')
                  .replace(/otp[:\s]+/gi, '')
                  .replace(/verification[:\s]+/gi, '')
                  .replace(/pin[:\s]+/gi, '');
        return otp.trim();
      }
    }
    
    return null;
  }

  async sendOTPToTelegram(sms) {
    try {
      const source = sms.source_addr || 'Unknown';
      const destination = sms.destination_addr || 'Unknown';
      const message = (sms.short_message || 'No content').replace(/\u0000/g, '');
      
      // Add 1 hour to timestamp
      let timestamp = sms.date || new Date().toLocaleString();
      if (sms.date) {
        const date = new Date(sms.date);
        date.setHours(date.getHours() + 1);
        timestamp = date.toISOString().replace('T', ' ').substring(0, 19);
      }
      
      const maskedDestination = this.maskPhoneNumber(destination);
      const extractedOTP = this.extractOTP(message);

      const formatted = `
╔══════════════════════════════╗
║  🔔 <b>NEW OTP RECEIVED</b> 🔔  ║
╚══════════════════════════════╝

📦 <b>Service:</b> ${source}

📱 <b>Phone:</b> ${maskedDestination}
${extractedOTP ? `
🔐 <b>OTP CODE:</b> <code>${extractedOTP}</code>
` : ''}
💬 <b>Full Message:</b>
<blockquote>${message}</blockquote>

🕐 ${timestamp}
──────────────────────────────`;

      for (const chatId of CONFIG.telegram_chat_ids) {
        try {
          await this.telegramBot.sendMessage(chatId, formatted, { parse_mode: 'HTML' });
          this.log('debug', `✅ OTP sent to channel ${chatId}`);
        } catch (err) {
          this.log('error', `❌ Failed to send OTP to ${chatId}: ${err.message}`);
        }
      }
      
      this.otpsSentCount++;
    } catch (err) {
      this.log('error', `❌ Telegram send error: ${err.message}`);
    }
  }

  async pollSMS() {
    if (this.isPolling) {
      this.log('debug', '⏭️ Poll in progress, skipping...');
      return;
    }
    
    this.isPolling = true;
    this.pollCount++;

    try {
      this.log('debug', `📊 Poll #${this.pollCount}`);
      const messages = await this.fetchLatestSMS();
      
      if (messages.length) {
        let newCount = 0;
        for (const sms of messages) {
          if (!this.sentMessageHashes.has(sms.hash)) {
            this.log('info', `🆕 New OTP from ${sms.source_addr} → ${sms.destination_addr}`);
            await this.sendOTPToTelegram(sms);
            this.sentMessageHashes.add(sms.hash);
            newCount++;
            
            if (this.sentMessageHashes.size > 1000) {
              const hashArray = Array.from(this.sentMessageHashes);
              this.sentMessageHashes = new Set(hashArray.slice(-500));
            }
          }
        }
        
        if (newCount > 0) {
          this.log('info', `✅ Sent ${newCount} OTP(s)`);
          this.saveSentMessages();
        }
      }
    } catch (err) {
      this.log('error', `❌ Poll error: ${err.message}`);
    } finally {
      this.isPolling = false;
    }
  }

  startPolling() {
    this.log('info', '⏱️ Starting SMS polling...');
    
    this.pollSMS();
    
    this.pollInterval = setInterval(() => {
      this.pollSMS();
    }, CONFIG.poll_interval);

    this.log('info', `✅ Polling started (every ${CONFIG.poll_interval / 1000}s)`);

    this.healthCheckInterval = setInterval(() => {
      this.performHealthCheck();
    }, 60000);
  }

  performHealthCheck() {
    const timeSinceLastPoll = Date.now() - this.lastSuccessfulPoll;
    const minutesAgo = Math.floor(timeSinceLastPoll / 60000);
    
    this.log('debug', `🏥 Health: Polls=${this.pollCount}, LastPoll=${minutesAgo}m ago, OTPs=${this.otpsSentCount}`);
    
    if (timeSinceLastPoll > 300000) {
      this.log('warn', '⚠️ No successful poll in 5 minutes - API may be down');
    }
  }

  setupTelegramHandlers() {
    this.telegramBot.onText(/\/start/, (msg) => {
      this.log('debug', `📱 /start command from ${msg.chat.id}`);
      this.telegramBot.sendMessage(
        msg.chat.id,
        `👑 <b>OTP King</b> is active and monitoring!\n\nUse /status to check connection status.`,
        { parse_mode: 'HTML' }
      );
    });

    this.telegramBot.onText(/\/status/, (msg) => {
      const uptime = process.uptime();
      const hours = Math.floor(uptime / 3600);
      const minutes = Math.floor((uptime % 3600) / 60);
      const timeSinceLastPoll = Date.now() - this.lastSuccessfulPoll;
      const minutesSinceLastPoll = Math.floor(timeSinceLastPoll / 60000);
      
      const statusMessage = `╔═══════════════════════════════════╗
║   👑 OTP KING - STATUS REPORT 👑   ║
╚═══════════════════════════════════╝

✅ <b>Status:</b> ${this.isRunning ? '🟢 Running' : '🔴 Stopped'}

📨 <b>OTPs Sent:</b> <code>${this.otpsSentCount}</code>

⏱️ <b>Poll Interval:</b> ${CONFIG.poll_interval / 1000}s

🌐 <b>API Status:</b> ✅ Active

📡 <b>Active Channels:</b> ${CONFIG.telegram_chat_ids.length}

📊 <b>Total Polls:</b> <code>${this.pollCount}</code>

🕐 <b>Last Poll:</b> ${minutesSinceLastPoll}m ago

⏰ <b>Uptime:</b> <code>${hours}h ${minutes}m</code>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`;
      
      this.telegramBot.sendMessage(msg.chat.id, statusMessage, { parse_mode: 'HTML' });
      this.log('debug', `📊 Status requested by ${msg.chat.id}`);
    });

    this.telegramBot.on('polling_error', (error) => {
      this.log('error', `❌ Telegram polling error: ${error.message}`);
    });

    this.log('info', '✅ Telegram handlers configured');
  }

  async start() {
    try {
      if (this.isRunning) {
        this.log('warn', '⚠️ Bot is already running');
        return;
      }

      this.log('info', '╔═══════════════════════════════════╗');
      this.log('info', '║   👑 OTP KING BOT STARTING 👑     ║');
      this.log('info', '╚═══════════════════════════════════╝');

      this.log('info', '🤖 Initializing Telegram bot...');
      this.telegramBot = new TelegramBot(CONFIG.telegram_bot_token, { polling: true });
      this.setupTelegramHandlers();
      this.log('info', '✅ Telegram bot connected');

      this.log('info', '🌐 Testing API connection...');
      const testMessages = await this.fetchLatestSMS();
      this.log('info', `✅ API connection successful (fetched ${testMessages.length} messages)`);

      await this.markExistingMessagesAsSent();

      this.startPolling();

      this.isRunning = true;

      this.log('info', '╔═══════════════════════════════════╗');
      this.log('info', '║   ✅ OTP KING STARTED SUCCESSFULLY ║');
      this.log('info', '╚═══════════════════════════════════╝');
      this.log('info', `📱 Telegram Token: ${CONFIG.telegram_bot_token.substring(0, 15)}...`);
      this.log('info', `🔑 API Token: ${CONFIG.api_token.substring(0, 15)}...`);
      this.log('info', `📡 Monitoring Channels: ${CONFIG.telegram_chat_ids.join(', ')}`);
      this.log('info', `⏱️ Poll Interval: ${CONFIG.poll_interval / 1000} seconds`);
      this.log('info', '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');

      // Send connection successful message to all channels
      await this.sendConnectionSuccessMessage();

    } catch (err) {
      this.log('error', `❌ Failed to start bot: ${err.message}`);
      await this.stop();
      process.exit(1);
    }
  }

  async stop() {
    try {
      this.log('info', '🛑 Stopping bot...');

      if (this.pollInterval) {
        clearInterval(this.pollInterval);
      }
      if (this.healthCheckInterval) {
        clearInterval(this.healthCheckInterval);
      }

      if (this.telegramBot) {
        this.telegramBot.stopPolling();
      }

      this.saveSentMessages();
      this.isRunning = false;

      this.log('info', '✅ Bot stopped');
    } catch (err) {
      this.log('error', `Error stopping bot: ${err.message}`);
    }
  }
}

const bot = new OTPKingBot();

process.on('SIGINT', async () => {
  console.log('\n');
  bot.log('info', '📴 Received SIGINT - shutting down gracefully...');
  await bot.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\n');
  bot.log('info', '📴 Received SIGTERM - shutting down gracefully...');
  await bot.stop();
  process.exit(0);
});

process.on('uncaughtException', (err) => {
  console.log('\n');
  bot.log('error', `💥 Uncaught Exception: ${err.message}`);
  bot.log('error', err.stack);
});

process.on('unhandledRejection', (reason, promise) => {
  bot.log('error', `💥 Unhandled Rejection at ${promise}: ${reason}`);
});

// ==================== HTTP HEALTH SERVER ====================
// Cloud Run requires container to listen on PORT - START THIS FIRST
const PORT = process.env.PORT || 8081;
const server = http.createServer((req, res) => {
  if (req.url === '/health' || req.url === '/' ) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'running',
      bot_name: 'OTP King',
      bot_active: bot && bot.isRunning,
      uptime: process.uptime(),
      otps_sent: bot ? bot.otpsSentCount : 0,
      polls: bot ? bot.pollCount : 0
    }));
  } else {
    res.writeHead(404);
    res.end('Not found');
  }
});

// Listen immediately with error handling
server.listen(PORT, '0.0.0.0', () => {
  console.log(`✅ [HTTP] Server listening on port ${PORT}`);
});

server.on('error', (err) => {
  console.log(`❌ [HTTP] Error: ${err.message}`);
  process.exit(1);
});

// ==================== START BOT IN BACKGROUND ====================
console.log('🤖 [STARTUP] Starting OTP King bot in background...\n');

// Start bot WITHOUT awaiting - this way HTTP server keeps listening
bot.start()
  .then(() => {
    console.log('\n✅ OTP King bot started successfully\n');
  })
  .catch(err => {
    console.log(`\n⚠️ Bot initialization error: ${err.message}\n`);
    console.log('HTTP server still listening for health checks\n');
  });
