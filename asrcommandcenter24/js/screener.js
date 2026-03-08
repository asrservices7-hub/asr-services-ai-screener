/* ==============================
   Screener — Advanced Multi-Criteria Scoring Engine
   ============================== */

const Screener = {
    /* ---------- Extract text from PDF using PDF.js ---------- */
    async extractPDFText(file) {
        const arrayBuffer = await file.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
        const pages = [];
        for (let i = 1; i <= pdf.numPages; i++) {
            const page = await pdf.getPage(i);
            const textContent = await page.getTextContent();
            const text = textContent.items.map(item => item.str).join(' ');
            pages.push(text);
        }
        return pages.join('\n');
    },

    /* ---------- Extract text from TXT ---------- */
    async extractTxtText(file) {
        return await file.text();
    },

    /* ---------- Extract text from DOCX using Mammoth ---------- */
    async extractDocxText(file) {
        try {
            const arrayBuffer = await file.arrayBuffer();
            const result = await mammoth.extractRawText({ arrayBuffer: arrayBuffer });
            return result.value || '';
        } catch (err) {
            console.error('Docx extraction error:', err);
            return '';
        }
    },

    /* ---------- Extract text from Image using Tesseract ---------- */
    async extractImageText(file) {
        try {
            const result = await Tesseract.recognize(file, 'eng');
            return result.data.text || '';
        } catch (err) {
            console.error('OCR error:', err);
            return '';
        }
    },

    /* ---------- Extract text from any supported file ---------- */
    async extractText(file) {
        const name = file.name.toLowerCase();
        if (name.endsWith('.pdf')) {
            return await this.extractPDFText(file);
        } else if (name.endsWith('.txt') || name.endsWith('.text')) {
            return await this.extractTxtText(file);
        } else if (name.endsWith('.doc') || name.endsWith('.docx')) {
            return await this.extractDocxText(file);
        } else if (name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg')) {
            return await this.extractImageText(file);
        }
        return '';
    },

    /* ---------- Tokenize ---------- */
    tokenize(text) {
        return text
            .toLowerCase()
            .replace(/[^a-z0-9\s\+\#\.\-]/g, ' ')
            .split(/\s+/)
            .filter(w => w.length > 1);
    },

    /* ==============================================
       CRITERIA 1: Skills Match (40% weight)
       ============================================== */
    scoreSkills(resumeText, requiredSkills) {
        const lower = resumeText.toLowerCase();
        const matched = [];
        const missing = [];

        for (const skill of requiredSkills) {
            const skillLower = skill.toLowerCase().trim();
            if (!skillLower) continue;

            // Check for exact word/phrase match
            if (lower.includes(skillLower)) {
                matched.push(skill);
            } else {
                // Check for common abbreviations / variations
                const variations = this.getSkillVariations(skillLower);
                let found = false;
                for (const v of variations) {
                    if (lower.includes(v)) {
                        matched.push(skill);
                        found = true;
                        break;
                    }
                }
                if (!found) missing.push(skill);
            }
        }

        const score = requiredSkills.length > 0
            ? (matched.length / requiredSkills.length) * 100
            : 0;

        return { score: Math.round(score), matched, missing };
    },

    getSkillVariations(skill) {
        const map = {
            'javascript': ['js', 'node.js', 'nodejs', 'ecmascript'],
            'typescript': ['ts'],
            'python': ['py', 'python3'],
            'react': ['react.js', 'reactjs'],
            'angular': ['angular.js', 'angularjs'],
            'vue': ['vue.js', 'vuejs'],
            'node': ['node.js', 'nodejs'],
            'express': ['express.js', 'expressjs'],
            'mongodb': ['mongo'],
            'postgresql': ['postgres', 'psql'],
            'mysql': ['sql'],
            'aws': ['amazon web services'],
            'gcp': ['google cloud', 'google cloud platform'],
            'azure': ['microsoft azure'],
            'docker': ['containerization'],
            'kubernetes': ['k8s'],
            'machine learning': ['ml', 'deep learning', 'dl'],
            'artificial intelligence': ['ai'],
            'natural language processing': ['nlp'],
            'c++': ['cpp', 'c plus plus'],
            'c#': ['csharp', 'c sharp'],
            '.net': ['dotnet', 'asp.net'],
            'ci/cd': ['cicd', 'continuous integration', 'continuous deployment'],
            'rest': ['restful', 'rest api', 'restful api'],
            'graphql': ['graph ql'],
            'html': ['html5'],
            'css': ['css3', 'scss', 'sass'],
            'java': ['jdk', 'spring boot', 'spring'],
            'php': ['laravel', 'codeigniter'],
            'ruby': ['ruby on rails', 'rails'],
            'swift': ['swiftui'],
            'kotlin': ['android'],
            'flutter': ['dart'],
            'react native': ['rn'],
            'power bi': ['powerbi'],
            'tableau': ['data visualization'],
            'excel': ['ms excel', 'microsoft excel', 'spreadsheet'],
            'figma': ['ui design', 'ux design'],
        };
        return map[skill] || [];
    },

    /* ==============================================
       CRITERIA 2: Overall Experience (15% weight)
       ============================================== */
    scoreOverallExperience(resumeText, requiredYears) {
        const years = this.extractTotalYears(resumeText);
        if (requiredYears <= 0) return { score: 100, years };

        if (years >= requiredYears) {
            return { score: 100, years };
        } else if (years >= requiredYears * 0.7) {
            // Within 70% — partial credit
            return { score: Math.round((years / requiredYears) * 100), years };
        } else {
            return { score: Math.round((years / requiredYears) * 50), years };
        }
    },

    extractTotalYears(text) {
        const lower = text.toLowerCase();
        let maxYears = 0;

        // Pattern: "X years of experience" or "X+ years" or "X yrs"
        const patterns = [
            /(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:experience|exp|work)/gi,
            /(?:experience|exp|work)\s*(?:of\s*)?(\d+)\+?\s*(?:years?|yrs?)/gi,
            /(\d+)\+?\s*(?:years?|yrs?)\s*(?:in\s+(?:the\s+)?(?:industry|field|domain))/gi,
            /total\s*(?:work\s*)?(?:experience|exp)\s*[:\-]?\s*(\d+)\+?\s*(?:years?|yrs?)/gi,
        ];

        for (const pattern of patterns) {
            let match;
            while ((match = pattern.exec(lower)) !== null) {
                const num = parseInt(match[1]);
                if (num > 0 && num < 50) {
                    maxYears = Math.max(maxYears, num);
                }
            }
        }

        // Fallback: look for date ranges to calculate experience
        if (maxYears === 0) {
            const yearNums = [];
            const yearPattern = /\b(20\d{2}|19\d{2})\b/g;
            let m;
            while ((m = yearPattern.exec(lower)) !== null) {
                yearNums.push(parseInt(m[1]));
            }
            if (yearNums.length >= 2) {
                const earliest = Math.min(...yearNums);
                const latest = Math.max(...yearNums);
                const span = latest - earliest;
                if (span > 0 && span < 50) maxYears = span;
            }
        }

        return maxYears;
    },

    /* ==============================================
       CRITERIA 3: Relevant Experience (20% weight)
       ============================================== */
    scoreRelevantExperience(resumeText, jobTitle, requiredYears) {
        const lower = resumeText.toLowerCase();
        const titleLower = jobTitle.toLowerCase().trim();
        const titleWords = titleLower.split(/\s+/).filter(w => w.length > 2);

        // Check if the job title or its key words appear near "years" or "experience"
        let relevantYears = 0;

        // Direct patterns like "5 years as software engineer"
        for (const word of titleWords) {
            const patterns = [
                new RegExp(`(\\d+)\\+?\\s*(?:years?|yrs?)\\s*(?:of\\s*)?(?:experience\\s*)?(?:as\\s*|in\\s*|with\\s*)?[^.]*${word}`, 'gi'),
                new RegExp(`${word}[^.]*?(\\d+)\\+?\\s*(?:years?|yrs?)`, 'gi'),
            ];
            for (const p of patterns) {
                let m;
                while ((m = p.exec(lower)) !== null) {
                    const n = parseInt(m[1]);
                    if (n > 0 && n < 50) relevantYears = Math.max(relevantYears, n);
                }
            }
        }

        // Also check if resume has the job title at all
        const hasTitleMatch = titleWords.filter(w => lower.includes(w)).length >= Math.ceil(titleWords.length * 0.5);

        if (relevantYears > 0 && requiredYears > 0) {
            const ratio = Math.min(relevantYears / requiredYears, 1);
            return { score: Math.round(ratio * 100), years: relevantYears, hasTitleMatch };
        } else if (hasTitleMatch) {
            return { score: 50, years: 0, hasTitleMatch: true };
        }
        return { score: 20, years: 0, hasTitleMatch };
    },

    /* ==============================================
       CRITERIA 4: Skill Usage Duration (10% weight)
       ============================================== */
    scoreSkillDuration(resumeText, requiredSkills, requiredYears) {
        const lower = resumeText.toLowerCase();
        let totalSkillYears = 0;
        let maxPossibleYears = requiredSkills.length * requiredYears;
        const skillYears = {};

        for (const skill of requiredSkills) {
            const s = skill.toLowerCase().trim();
            if (!s) continue;

            // Try "X years of [skill]" patterns
            const patterns = [
                new RegExp(`(\\d+)\\+?\\s*(?:years?|yrs?)\\s*(?:of\\s*)?(?:experience\\s*)?(?:with\\s*|in\\s*|using\\s*)?${s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'gi'),
                new RegExp(`${s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}[^.]{0,40}?(\\d+)\\+?\\s*(?:years?|yrs?)`, 'gi'),
            ];

            let yrs = 0;
            for (const p of patterns) {
                let m;
                while ((m = p.exec(lower)) !== null) {
                    const n = parseInt(m[1]);
                    if (n > 0 && n < 30) yrs = Math.max(yrs, n);
                }
            }

            // Fallback: if skill is mentioned, give at least 1 year credit
            if (yrs === 0 && lower.includes(s)) {
                yrs = 1;
            }

            skillYears[skill] = yrs;
            totalSkillYears += yrs;
        }

        if (maxPossibleYears <= 0) return { score: 100, skillYears };
        const score = Math.min(Math.round((totalSkillYears / maxPossibleYears) * 100), 100);
        return { score, skillYears };
    },

    /* ==============================================
       CRITERIA 5: Location Proximity (15% weight)
       ============================================== */
    scoreLocation(resumeText, hiringLocation) {
        if (!hiringLocation || !hiringLocation.trim()) return { score: 100, found: 'N/A (no location required)' };

        const lower = resumeText.toLowerCase();
        const locLower = hiringLocation.toLowerCase().trim();
        const locWords = locLower.split(/[\s,]+/).filter(w => w.length > 2);

        // Exact city/location match
        if (lower.includes(locLower)) {
            return { score: 100, found: hiringLocation };
        }

        // Partial match (e.g. "Bangalore" matches "Bengaluru")
        const cityAliases = {
            'bangalore': ['bengaluru', 'blr'],
            'bengaluru': ['bangalore', 'blr'],
            'mumbai': ['bombay'],
            'bombay': ['mumbai'],
            'chennai': ['madras'],
            'madras': ['chennai'],
            'kolkata': ['calcutta'],
            'calcutta': ['kolkata'],
            'delhi': ['new delhi', 'ncr', 'noida', 'gurgaon', 'gurugram', 'faridabad', 'ghaziabad'],
            'ncr': ['delhi', 'new delhi', 'noida', 'gurgaon', 'gurugram'],
            'noida': ['delhi', 'ncr', 'greater noida'],
            'gurgaon': ['gurugram', 'delhi', 'ncr'],
            'gurugram': ['gurgaon', 'delhi', 'ncr'],
            'hyderabad': ['hyd', 'secunderabad'],
            'pune': ['puna'],
            'ahmedabad': ['amdavad'],
            'thiruvananthapuram': ['trivandrum'],
            'trivandrum': ['thiruvananthapuram'],
            'kochi': ['cochin'],
            'cochin': ['kochi'],
            'varanasi': ['banaras', 'benaras'],
            'new york': ['nyc', 'manhattan'],
            'san francisco': ['sf', 'bay area'],
            'los angeles': ['la'],
            'london': ['ldn'],
            'remote': ['work from home', 'wfh', 'anywhere', 'remote'],
        };

        // Check aliases
        for (const word of locWords) {
            if (lower.includes(word)) {
                return { score: 90, found: word };
            }
            const aliases = cityAliases[word] || [];
            for (const alias of aliases) {
                if (lower.includes(alias)) {
                    return { score: 85, found: alias + ' (alias of ' + word + ')' };
                }
            }
        }

        // Check for "willing to relocate" or "open to relocation"
        const relocatePatterns = [
            /(?:willing|open|ready)\s*(?:to\s*)?(?:relocat|move|shift)/i,
            /relocat(?:e|ion|ing)/i,
        ];
        for (const p of relocatePatterns) {
            if (p.test(lower)) {
                return { score: 60, found: 'Willing to relocate' };
            }
        }

        // Check for "remote" preference
        if (/\b(?:remote|wfh|work\s*from\s*home)\b/i.test(lower)) {
            return { score: 40, found: 'Remote preference (location mismatch)' };
        }

        return { score: 0, found: 'No location match found' };
    },

    /* ==============================================
       COMPOSITE SCORING
       ============================================== */
    calculateComposite(criteria) {
        // Weights
        const weights = {
            skills: 0.40,
            overallExp: 0.15,
            relevantExp: 0.20,
            skillDuration: 0.10,
            location: 0.15,
        };

        const composite = Math.round(
            criteria.skills.score * weights.skills +
            criteria.overallExp.score * weights.overallExp +
            criteria.relevantExp.score * weights.relevantExp +
            criteria.skillDuration.score * weights.skillDuration +
            criteria.location.score * weights.location
        );

        return Math.min(composite, 100);
    },

    /* ==============================================
       GENERATE REJECTION REASON
       ============================================== */
    getRejectionReason(criteria, threshold) {
        const reasons = [];

        if (criteria.skills.score < 30) {
            reasons.push(`Only ${criteria.skills.matched.length}/${criteria.skills.matched.length + criteria.skills.missing.length} required skills found`);
        }
        if (criteria.overallExp.score < 50) {
            reasons.push(`Insufficient experience (${criteria.overallExp.years} yrs found)`);
        }
        if (criteria.relevantExp.score < 30) {
            reasons.push('Lacks relevant role experience');
        }
        if (criteria.location.score === 0) {
            reasons.push(`Location mismatch — ${criteria.location.found}`);
        }
        if (criteria.skillDuration.score < 20) {
            reasons.push('Minimal demonstrated skill usage');
        }

        if (reasons.length === 0) {
            reasons.push(`Score ${criteria.composite}% below ${threshold}% threshold`);
        }

        // Return the most critical reason as a 1-liner
        return reasons[0];
    },

    /* ==============================================
       MAIN PROCESSING FUNCTION
       ============================================== */
    async processResumes(config, resumeFiles, onProgress) {
        const {
            jdText,
            requiredSkills,
            jobTitle,
            requiredYears,
            hiringLocation,
            passThreshold
        } = config;

        const results = [];
        const total = resumeFiles.length;

        for (let i = 0; i < total; i++) {
            const file = resumeFiles[i];
            try {
                const text = await this.extractText(file);

                // Score each criterion
                const skills = this.scoreSkills(text, requiredSkills);
                const overallExp = this.scoreOverallExperience(text, requiredYears);
                const relevantExp = this.scoreRelevantExperience(text, jobTitle, requiredYears);
                const skillDuration = this.scoreSkillDuration(text, requiredSkills, requiredYears);
                const location = this.scoreLocation(text, hiringLocation);

                const criteria = { skills, overallExp, relevantExp, skillDuration, location };
                criteria.composite = this.calculateComposite(criteria);

                const selected = criteria.composite >= passThreshold;
                const rejectionReason = selected ? null : this.getRejectionReason(criteria, passThreshold);

                results.push({
                    fileName: file.name,
                    fileSize: file.size,
                    composite: criteria.composite,
                    selected,
                    rejectionReason,
                    criteria
                });

            } catch (err) {
                results.push({
                    fileName: file.name,
                    fileSize: file.size,
                    composite: 0,
                    selected: false,
                    rejectionReason: 'Error parsing file: ' + err.message,
                    criteria: {
                        skills: { score: 0, matched: [], missing: requiredSkills },
                        overallExp: { score: 0, years: 0 },
                        relevantExp: { score: 0, years: 0, hasTitleMatch: false },
                        skillDuration: { score: 0, skillYears: {} },
                        location: { score: 0, found: 'N/A' },
                        composite: 0
                    },
                    error: err.message
                });
            }

            if (onProgress) onProgress(i + 1, total, file.name);
        }

        // Separate and sort
        const selected = results
            .filter(r => r.selected)
            .sort((a, b) => b.composite - a.composite); // Highest first

        const rejected = results
            .filter(r => !r.selected)
            .sort((a, b) => b.composite - a.composite); // Nearest to threshold first

        return { selected, rejected, total: results.length, requiredSkills, passThreshold };
    }
};
