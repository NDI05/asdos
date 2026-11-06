import { describe, expect, it } from 'vitest';
import { questionSeeds, splitQuestionText, jobError } from './workflow';

describe('question and weight workflow', () => {
  it('splits the supplied two-question format and preserves Linux paths', () => {
    const questions = splitQuestionText('Waktu 15 menit.\n1. Jelaskan /proc, /sys, dan /dev.\nMengapa tidak di disk?\n2. Uraikan /etc/hosts dan /etc/resolv.conf.');
    expect(questions).toHaveLength(2);
    expect(questions[0].text).toContain('/proc');
    expect(questions[0].text).not.toContain('Waktu');
    expect(questions[1].text).toContain('/etc/resolv.conf');
    expect(questions[1].weight).toBe('1');
  });
  it('sends questions and weights without requiring teacher answers', () => {
    const seeds = splitQuestionText('1. Apa RAM?').map(q => ({...q, reference_answer:'DO_NOT_SEND', criteria:[]}));
    expect(questionSeeds(seeds)[0]).not.toHaveProperty('reference_answer');
    expect(questionSeeds(seeds)[0].weight).toBe('1');
  });
  it('does not silently merge duplicate numbering', () => {
    expect(()=>splitQuestionText('1. A\n1. B')).toThrow('berulang');
  });
  it('explains unavailable model and unreadable answers', () => {
    expect(jobError('MODEL_UNAVAILABLE')).toContain('belum disiapkan');
    expect(jobError('UNREADABLE_TRANSCRIPTION_REVIEW_REQUIRED')).toContain('tidak terbaca');
  });
});
