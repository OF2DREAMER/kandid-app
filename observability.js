/**
 * Kindid — Safety-First Production Observability Module (observability.js)
 *
 * Strict Privacy & Security Guarantees:
 * - P0: Zero exposure of sensitive fields (passwords, OTPs, auth tokens, cookies, chat texts, GPS, media bytes).
 * - Strict per-event property allowlists; any unapproved key is automatically discarded.
 * - Deep sanitization of string and numeric values.
 * - Session Replay is hard-disabled (never enabled without dedicated privacy review).
 * - Complete fail-safe: Telemetry failures are silent no-ops and NEVER crash or block user flows.
 */

(function(window) {
  'use strict';

  // 1. Strict Regex for Sensitive Field Redaction
  var SENSITIVE_KEY_REGEX = /password|token|secret|auth|bearer|cookie|otp|code|pin|credential|session|key|private|email|phone|lat|lon|coord|gps|audio|photo|img|image|caption|message|text|detail|body/i;
  var SENSITIVE_VALUE_REGEX = /(@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})|(bearer\s+[a-zA-Z0-9_\-\.]+)|(token_[a-zA-Z0-9_\-]+)|([a-f0-9]{32,64})/i;

  // 2. Exact Property Allowlists per Event Name
  var EVENT_PROPERTY_ALLOWLIST = {
    'signup_started': ['method'],
    'signup_completed': ['method'],
    'login_success': ['method'],
    'login_failed': ['method', 'error_category'],
    'google_login_success': ['is_new_user'],
    'google_login_failed': ['error_category'],
    'onboarding_started': ['step'],
    'onboarding_completed': ['duration_ms'],
    'feed_loaded': ['circle', 'count'],
    'feed_load_failed': ['circle', 'error_category'],
    'camera_opened': ['source'],
    'capture_started': ['mode'],
    'capture_completed': ['has_audio', 'duration_ms'],
    'post_publish_success': ['is_perspective', 'circle'],
    'post_publish_failed': ['is_perspective', 'error_category'],
    'perspective_started': ['cluster_id'],
    'perspective_submitted': ['cluster_id'],
    'community_viewed': ['community_id', 'type'],
    'community_joined': ['community_id'],
    'community_created': ['type'],
    'chat_opened': ['conversation_type'],
    'message_send_success': ['has_attachment'],
    'message_send_failed': ['error_category'],
    'report_submitted': ['target_type', 'reason_category'],
    'block_action': ['action'],
    'api_metric': ['endpoint', 'method', 'status', 'duration_ms', 'success', 'error_category'],
    'error_captured': ['error_category', 'sanitized_message', 'source', 'lineno', 'colno']
  };

  // 3. Module State
  var state = {
    initialized: false,
    enabled: false,
    posthogApiKey: '',
    posthogHost: 'https://us.i.posthog.com',
    appVersion: '5.2.2',
    environment: (typeof location !== 'undefined' && (location.hostname === 'localhost' || location.hostname === '127.0.0.1')) ? 'development' : 'production',
    debug: false,
    distinctId: ''
  };

  // 4. Value Sanitization Helper
  function sanitizeValue(val) {
    if (val === null || val === undefined) return null;
    if (typeof val === 'boolean') return val;
    if (typeof val === 'number') {
      if (!isFinite(val)) return 0;
      return Math.round(val * 100) / 100; // 2 decimal precision
    }
    if (typeof val === 'string') {
      var str = val.trim();
      if (str.length === 0) return '';
      // Check for sensitive patterns
      if (SENSITIVE_VALUE_REGEX.test(str)) {
        return '[REDACTED]';
      }
      // Truncate to maximum 64 characters and strip unsafe control characters
      return str.substring(0, 64).replace(/[^\x20-\x7E]/g, '');
    }
    // Reject objects, arrays, functions, etc.
    return null;
  }

  // 5. Endpoint Path Normalizer for API Telemetry
  function normalizeEndpoint(rawEndpoint) {
    if (!rawEndpoint || typeof rawEndpoint !== 'string') return '/api/unknown';
    try {
      var path = rawEndpoint.split('?')[0].split('#')[0].trim();
      // Replace IDs like /api/moment/m_abc123/i-was-there with /api/moment/:id/i-was-there
      path = path.replace(/\/api\/moment\/[^\/]+\/i-was-there/, '/api/moment/:id/i-was-there');
      path = path.replace(/\/api\/moment\/[^\/]+\/eligibility/, '/api/moment/:id/eligibility');
      path = path.replace(/\/api\/cluster\/[^\/]+/, '/api/cluster/:id');
      path = path.replace(/\/api\/user\/[^\/]+/, '/api/user/:id');
      path = path.replace(/\/api\/community\/health\/[^\/]+/, '/api/community/health/:id');
      return path.substring(0, 64);
    } catch (e) {
      return '/api/unknown';
    }
  }

  // 6. Property Filter & Sanitizer
  function sanitizeProperties(eventName, props) {
    if (!props || typeof props !== 'object') return {};
    var allowedKeys = EVENT_PROPERTY_ALLOWLIST[eventName] || [];
    var safeProps = {
      app_version: state.appVersion,
      env: state.environment
    };

    for (var i = 0; i < allowedKeys.length; i++) {
      var key = allowedKeys[i];
      if (props.hasOwnProperty(key)) {
        // Redundancy check: ensure key does not match sensitive regex
        if (SENSITIVE_KEY_REGEX.test(key)) {
          continue;
        }
        var cleaned = sanitizeValue(props[key]);
        if (cleaned !== null) {
          safeProps[key] = cleaned;
        }
      }
    }
    return safeProps;
  }

  // 7. Internal Event Dispatcher (Fail-Safe)
  function dispatchTelemetry(eventName, properties) {
    if (!state.enabled && !state.debug) return;

    try {
      // Development console debugging
      if (state.debug && typeof console !== 'undefined' && console.debug) {
        console.debug('[Observability]', eventName, properties);
      }

      // If PostHog global exists, use its capture method
      if (typeof window !== 'undefined' && window.posthog && typeof window.posthog.capture === 'function') {
        window.posthog.capture(eventName, properties);
        return;
      }

      // If PostHog API Key is configured but SDK is not loaded, use lightweight fetch
      if (state.enabled && state.posthogApiKey && typeof fetch === 'function') {
        var payload = {
          api_key: state.posthogApiKey,
          event: eventName,
          properties: properties,
          timestamp: new Date().toISOString()
        };
        fetch(state.posthogHost + '/capture/', {
          method: 'POST',
          mode: 'cors',
          keepalive: true,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).catch(function() {
          // Silent no-op on network failure
        });
      }
    } catch (err) {
      // Telemetry must NEVER throw or break the app
    }
  }

  // 8. Public API
  var Observability = {
    /**
     * Initializes the observability module with optional environment config.
     */
    init: function(config) {
      try {
        config = config || {};
        if (config.apiKey) state.posthogApiKey = String(config.apiKey).trim();
        if (config.host) state.posthogHost = String(config.host).trim();
        if (config.appVersion) state.appVersion = String(config.appVersion).trim();
        if (config.environment) state.environment = String(config.environment).trim();
        if (typeof config.enabled === 'boolean') {
          state.enabled = config.enabled;
        } else {
          state.enabled = Boolean(state.posthogApiKey);
        }
        if (typeof config.debug === 'boolean') {
          state.debug = config.debug;
        } else {
          state.debug = (state.environment === 'development');
        }
        state.initialized = true;

        if (state.debug && typeof console !== 'undefined' && console.info) {
          console.info('[Observability] Initialized. Status: ' + (state.enabled ? 'ACTIVE' : 'STANDBY (no API key)'));
        }
      } catch (e) {
        // Fail-safe
      }
    },

    /**
     * Captures a high-signal, privacy-cleansed product event.
     */
    captureEvent: function(eventName, rawProperties) {
      try {
        if (!eventName || typeof eventName !== 'string') return;
        // Verify event is in known taxonomy
        if (!EVENT_PROPERTY_ALLOWLIST.hasOwnProperty(eventName)) {
          if (state.debug && typeof console !== 'undefined') {
            console.warn('[Observability] Rejected event outside taxonomy:', eventName);
          }
          return;
        }
        var sanitizedProps = sanitizeProperties(eventName, rawProperties || {});
        dispatchTelemetry(eventName, sanitizedProps);
      } catch (e) {
        // Fail-safe
      }
    },

    /**
     * Captures a sanitized frontend runtime error.
     */
    captureError: function(error, context) {
      try {
        var errCategory = 'Error';
        var errMsg = 'Unknown error';
        if (error) {
          if (typeof error === 'string') {
            errMsg = error;
          } else if (error.message) {
            errMsg = error.message;
            if (error.name) errCategory = error.name;
          }
        }
        // Sanitize message: strip tokens, URLs with query strings, emails
        errMsg = String(errMsg).replace(/[?&][^=]+=[^&\s]+/g, '')
                               .replace(/@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '[REDACTED_EMAIL]')
                               .replace(/bearer\s+[a-zA-Z0-9_\-\.]+/gi, '[REDACTED_TOKEN]')
                               .substring(0, 100);

        var payload = {
          error_category: errCategory.substring(0, 32),
          sanitized_message: errMsg,
          source: (context && context.source) ? String(context.source).substring(0, 32) : 'app',
          lineno: (context && typeof context.lineno === 'number') ? context.lineno : 0,
          colno: (context && typeof context.colno === 'number') ? context.colno : 0
        };

        var sanitizedProps = sanitizeProperties('error_captured', payload);
        dispatchTelemetry('error_captured', sanitizedProps);
      } catch (e) {
        // Fail-safe
      }
    },

    /**
     * Captures sanitized API telemetry without payload or header inspection.
     */
    captureApiMetric: function(metric) {
      try {
        if (!metric || typeof metric !== 'object') return;
        var cleanEndpoint = normalizeEndpoint(metric.endpoint);
        var cleanMethod = (metric.method || 'GET').toUpperCase();
        var status = (typeof metric.status === 'number') ? metric.status : 0;
        var duration = (typeof metric.duration_ms === 'number') ? Math.max(0, Math.round(metric.duration_ms)) : 0;
        var success = Boolean(metric.success);
        var errorCategory = metric.error_category ? String(metric.error_category).substring(0, 32) : '';

        var payload = {
          endpoint: cleanEndpoint,
          method: cleanMethod,
          status: status,
          duration_ms: duration,
          success: success,
          error_category: errorCategory
        };

        var sanitizedProps = sanitizeProperties('api_metric', payload);
        dispatchTelemetry('api_metric', sanitizedProps);
      } catch (e) {
        // Fail-safe
      }
    },

    /**
     * Exposes current configuration (read-only safe copy).
     */
    getConfig: function() {
      return {
        enabled: state.enabled,
        appVersion: state.appVersion,
        environment: state.environment,
        debug: state.debug,
        sessionRecordingEnabled: false // ALWAYS false
      };
    },

    /**
     * Direct property sanitizer exposed for unit testing.
     */
    _sanitizeProperties: sanitizeProperties,
    _normalizeEndpoint: normalizeEndpoint
  };

  // 9. Global Error Boundary Hooks (Fail-Safe)
  if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
    window.addEventListener('error', function(event) {
      try {
        if (event) {
          Observability.captureError(event.error || event.message, {
            source: event.filename ? event.filename.split('/').pop() : 'window',
            lineno: event.lineno,
            colno: event.colno
          });
        }
      } catch (e) {
        // Fail-safe
      }
    });

    window.addEventListener('unhandledrejection', function(event) {
      try {
        if (event && event.reason) {
          Observability.captureError(event.reason, {
            source: 'unhandled_promise'
          });
        }
      } catch (e) {
        // Fail-safe
      }
    });
  }

  // Export to global scope
  window.KandidObservability = Observability;

})(typeof window !== 'undefined' ? window : this);
