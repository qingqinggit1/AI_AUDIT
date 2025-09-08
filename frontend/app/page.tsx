"use client";

import { useState } from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CheckCircle2, Clock, FileText, Loader2, AlertCircle, Play } from "lucide-react";

interface RequirementItem {
  index: number;
  requirement: string;
  meta?: {
    chunk_index?: number;
    index_in_chunk?: number;
    total_in_chunk?: number;
  };
}

interface AuditResult {
  index: number;
  requirement: string;
  result?: string;
  status: 'pending' | 'processing' | 'completed';
}

type AuditEvent =
  | { type: "session"; session_id: string; file_id?: string | number }
  | { type: "vectorize_ok"; file_id?: string | number; user_id?: number; embedding_result?: boolean }
  | { type: "requirements_ready"; total: number; items: RequirementItem[] }
  | { type: "audit_begin"; index: number; requirement: string; meta?: any }
  | { type: "audit_end"; index: number; result: string }
  | { type: "done"; message: string; session_id?: string; total?: number }
  | { type: "unknown"; raw: any };

export default function Home() {
  const [requirementsContent, setRequirementsContent] = useState('');
  const [docsContent, setDocsContent] = useState('');
  const [isAuditing, setIsAuditing] = useState(false);
  const [sessionId, setSessionId] = useState<string>('');
  const [vectorizeStatus, setVectorizeStatus] = useState<boolean>(false);
  const [auditResults, setAuditResults] = useState<AuditResult[]>([]);
  const [currentProcessing, setCurrentProcessing] = useState<number>(-1);
  const [totalRequirements, setTotalRequirements] = useState<number>(0);
  const [completedCount, setCompletedCount] = useState<number>(0);
  const [isDone, setIsDone] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  const parseSSE = async (response: Response, onEvent: (eventName: string, data: any) => void) => {
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventName = '';
        let eventData = '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventName = line.substring(6).trim();
          } else if (line.startsWith('data:')) {
            eventData = line.substring(5).trim();
          } else if (line === '') {
            if (eventName && eventData) {
              try {
                const parsedData = JSON.parse(eventData);
                onEvent(eventName, parsedData);
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
            eventName = '';
            eventData = '';
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  };

  const mapToAuditEvent = (eventName: string, data: any): AuditEvent => {
    switch (eventName) {
      case "session": return { type: "session", ...data };
      case "vectorize_ok": return { type: "vectorize_ok", ...data };
      case "requirements_ready": return { type: "requirements_ready", ...data };
      case "audit_begin": return { type: "audit_begin", ...data };
      case "audit_end": return { type: "audit_end", ...data };
      case "done": return { type: "done", ...data };
      default: return { type: "unknown", raw: { eventName, data } };
    }
  };

  const handleSubmit = async () => {
    if (!requirementsContent.trim() || !docsContent.trim()) {
      setError('请填写审计要求和文档内容');
      return;
    }

    setError('');
    setIsAuditing(true);
    setSessionId('');
    setVectorizeStatus(false);
    setAuditResults([]);
    setCurrentProcessing(-1);
    setTotalRequirements(0);
    setCompletedCount(0);
    setIsDone(false);

    try {
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
      const response = await fetch(`${apiBaseUrl}/api/audit`, {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          requirements_content: requirementsContent,
          docs_contents: [docsContent],
          user_id: 1,
          file_id: Date.now().toString(),
          file_name: 'audit_document.txt'
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      await parseSSE(response, (eventName, data) => {
        const event: AuditEvent = mapToAuditEvent(eventName, data);
        
        switch (event.type) {
          case "session":
            setSessionId(event.session_id);
            break;
            
          case "vectorize_ok":
            setVectorizeStatus(event.embedding_result || false);
            break;
            
          case "requirements_ready":
            setTotalRequirements(event.total);
            const initialResults: AuditResult[] = event.items.map(item => ({
              index: item.index,
              requirement: item.requirement,
              status: 'pending' as const
            }));
            setAuditResults(initialResults);
            break;
            
          case "audit_begin":
            setCurrentProcessing(event.index);
            setAuditResults(prev => prev.map(result => 
              result.index === event.index 
                ? { ...result, status: 'processing' as const }
                : result
            ));
            break;
            
          case "audit_end":
            setAuditResults(prev => prev.map(result => 
              result.index === event.index 
                ? { ...result, result: event.result, status: 'completed' as const }
                : result
            ));
            setCompletedCount(prev => prev + 1);
            setCurrentProcessing(-1);
            break;
            
          case "done":
            setIsDone(true);
            setIsAuditing(false);
            break;
            
          default:
            console.log('Unknown event:', event);
        }
      });
    } catch (error) {
      console.error('Audit failed:', error);
      setError(error instanceof Error ? error.message : '审计过程中发生错误');
      setIsAuditing(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'processing':
        return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />;
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'processing':
        return <Badge variant="secondary" className="bg-blue-50 text-blue-700">审计中</Badge>;
      case 'completed':
        return <Badge variant="secondary" className="bg-green-50 text-green-700">已完成</Badge>;
      default:
        return <Badge variant="outline">待审计</Badge>;
    }
  };

  const progressPercentage = totalRequirements > 0 ? (completedCount / totalRequirements) * 100 : 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <div className="container mx-auto py-8 px-4 max-w-6xl">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">智能文档审计系统</h1>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            基于AI技术的自动化文档合规性审计平台，提供精确的要求匹配和详细的审计报告
          </p>
        </div>

        {/* Input Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <Card className="shadow-lg border-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-600" />
                审计要求
              </CardTitle>
              <CardDescription>
                请输入需要审计的具体要求内容，支持多条要求
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                placeholder="请输入审计要求，例如：&#10;1. 文档应包含风险评估章节&#10;2. 必须有明确的责任人分配&#10;3. 应包含时间节点规划..."
                value={requirementsContent}
                onChange={(e) => setRequirementsContent(e.target.value)}
                className="min-h-[200px] resize-none"
                disabled={isAuditing}
              />
            </CardContent>
          </Card>

          <Card className="shadow-lg border-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-green-600" />
                待审计文档
              </CardTitle>
              <CardDescription>
                请输入需要被审计的文档内容
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                placeholder="请输入待审计的文档内容..."
                value={docsContent}
                onChange={(e) => setDocsContent(e.target.value)}
                className="min-h-[200px] resize-none"
                disabled={isAuditing}
              />
            </CardContent>
          </Card>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert className="mb-6 border-red-200 bg-red-50">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <AlertDescription className="text-red-700">
              {error}
            </AlertDescription>
          </Alert>
        )}

        {/* Submit Button */}
        <div className="flex justify-center mb-8">
          <Button 
            onClick={handleSubmit} 
            disabled={isAuditing || !requirementsContent.trim() || !docsContent.trim()}
            size="lg"
            className="px-8 py-3 text-lg font-medium"
          >
            {isAuditing ? (
              <>
                <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                审计进行中...
              </>
            ) : (
              <>
                <Play className="w-5 h-5 mr-2" />
                开始审计
              </>
            )}
          </Button>
        </div>

        {/* Status Section */}
        {isAuditing && (
          <Card className="mb-6 shadow-lg border-0">
            <CardHeader>
              <CardTitle>审计状态</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between text-sm">
                <span>会话ID</span>
                <Badge variant="outline">{sessionId || '初始化中...'}</Badge>
              </div>
              
              <div className="flex items-center justify-between text-sm">
                <span>向量化状态</span>
                <div className="flex items-center gap-2">
                  {vectorizeStatus ? (
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                  ) : (
                    <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                  )}
                  <span>{vectorizeStatus ? '完成' : '处理中...'}</span>
                </div>
              </div>

              {totalRequirements > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span>审计进度</span>
                    <span>{completedCount} / {totalRequirements}</span>
                  </div>
                  <Progress value={progressPercentage} className="w-full" />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Results Section */}
        {auditResults.length > 0 && (
          <Card className="shadow-lg border-0">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>审计结果</span>
                {isDone && (
                  <Badge variant="secondary" className="bg-green-50 text-green-700">
                    审计完成
                  </Badge>
                )}
              </CardTitle>
              <CardDescription>
                {isDone 
                  ? `已完成 ${auditResults.length} 项审计要求的检查`
                  : `正在审计第 ${currentProcessing + 1} 项，共 ${auditResults.length} 项`
                }
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[600px] pr-4">
                <div className="space-y-4">
                  {auditResults.map((result, index) => (
                    <Card key={result.index} className={`border transition-all duration-300 ${
                      result.status === 'processing' ? 'border-blue-200 bg-blue-50' : 
                      result.status === 'completed' ? 'border-green-200' : 'border-gray-200'
                    }`}>
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          {getStatusIcon(result.status)}
                          <div className="flex-1 space-y-2">
                            <div className="flex items-center justify-between">
                              <h4 className="font-medium text-gray-900">
                                审计要求 {result.index + 1}
                              </h4>
                              {getStatusBadge(result.status)}
                            </div>
                            
                            <p className="text-gray-700 text-sm leading-relaxed">
                              {result.requirement}
                            </p>
                            
                            {result.result && (
                              <>
                                <Separator className="my-3" />
                                <div className="bg-gray-50 p-3 rounded-lg">
                                  <h5 className="font-medium text-gray-900 mb-2">审计结果：</h5>
                                  <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                                    {result.result}
                                  </div>
                                </div>
                              </>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}