/* Generated from contracts/*.schema.json. Do not edit. */

export type AnalysisContract = AnalysisSuccess | AnalysisError | AnalysisStatus;
export type RequestId = string;
export type ErrorCode =
  | "INVALID_REQUEST"
  | "EMAIL_TOO_LARGE"
  | "EMPTY_EMAIL"
  | "INVALID_EMAIL"
  | "INSUFFICIENT_CONTENT"
  | "RESOURCE_LIMIT"
  | "SERVICE_BUSY"
  | "MODEL_UNAVAILABLE"
  | "UPSTREAM_UNAVAILABLE"
  | "ANALYSIS_TIMEOUT"
  | "UPSTREAM_INVALID_RESPONSE"
  | "INTERNAL_ERROR";

export interface AnalysisSuccess {
  analysis_status: "completed";
  label: "legit" | "spam_or_phishing" | "phishing";
  explanation?: Explanation;
}
export interface Explanation {
  /**
   * @minItems 1
   * @maxItems 5
   */
  factors:
    | [ExplanationFactor]
    | [ExplanationFactor, ExplanationFactor]
    | [ExplanationFactor, ExplanationFactor, ExplanationFactor]
    | [ExplanationFactor, ExplanationFactor, ExplanationFactor, ExplanationFactor]
    | [ExplanationFactor, ExplanationFactor, ExplanationFactor, ExplanationFactor, ExplanationFactor];
}
export interface ExplanationFactor {
  factor: string;
  direction: "positive" | "negative";
  strength: number;
}
export interface AnalysisError {
  request_id: RequestId;
  error: {
    code: ErrorCode;
    message: string;
  };
}
export interface AnalysisStatus {
  request_id: RequestId;
  phase: "unknown" | "starting" | "receiving" | "processing";
}

/* Generated from contracts/*.schema.json. Do not edit. */

export interface TransportPolicy {
  version: 1;
  limits: {
    fileBytes: number;
    multipartBytes: number;
    mimeParts: number;
    mimeDepth: number;
    decodedBytes: number;
    tokens: number;
    allowedParserDefects: string[];
  };
  deadlines: {
    browserMs: number;
    proxyMs: number;
    backendMs: number;
    workerStartupMs: number;
    backendReserveMs: number;
    clockSkewMs: number;
    terminateMs: number;
    killReapMs: number;
  };
  retry: {
    maxRetries: number;
  };
  polling: {
    intervalMs: number;
    maxPolls: number;
    timeoutMs: number;
  };
  errors: {
    INVALID_REQUEST: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    EMAIL_TOO_LARGE: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    EMPTY_EMAIL: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    INVALID_EMAIL: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    INSUFFICIENT_CONTENT: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    RESOURCE_LIMIT: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    SERVICE_BUSY: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    MODEL_UNAVAILABLE: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    UPSTREAM_UNAVAILABLE: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    ANALYSIS_TIMEOUT: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    UPSTREAM_INVALID_RESPONSE: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
    INTERNAL_ERROR: {
      http: number;
      retryAfterSeconds: number;
      message: string;
    };
  };
}
