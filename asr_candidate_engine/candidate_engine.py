import json

class CandidateEngine:
    def __init__(self, db_path="candidates.json"):
        self.db_path = db_path
        self.candidates = self._load_db()

    def _load_db(self):
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def add_candidate(self, name, skills, experience):
        candidate = {
            "name": name,
            "skills": skills,
            "experience": experience,
            "score": self._calculate_score(skills, experience)
        }
        self.candidates.append(candidate)
        self._save_db()
        return candidate

    def _calculate_score(self, skills, experience):
        # Basic scoring logic: 10 points per skill + 5 points per year of experience
        score = len(skills) * 10 + experience * 5
        return min(score, 100) # Cap at 100

    def _save_db(self):
        with open(self.db_path, 'w') as f:
            json.dump(self.candidates, f, indent=4)

    def get_top_candidates(self, n=5):
        return sorted(self.candidates, key=lambda x: x['score'], reverse=True)[:n]

if __name__ == "__main__":
    engine = CandidateEngine()
    engine.add_candidate("Alex Rivera", ["Python", "React", "Node.js"], 8)
    engine.add_candidate("Sarah Chen", ["Python", "Machine Learning", "Statistics"], 5)
    
    print("Top Candidates:")
    for c in engine.get_top_candidates():
        print(f"{c['name']}: {c['score']}% Match")
