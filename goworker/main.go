package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"os/signal"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/gorilla/websocket"
)

const (
	gqlURL        = "https://gql.twitch.tv/gql"
	validateURL   = "https://id.twitch.tv/oauth2/validate"
	clientID      = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
	userAgent     = "Dalvik/2.1.0 (Linux; U; Android 13; SM-G991B Build/TP1A.220624.014) tv.twitch.android.app/29.9.1/2909016"
	inventoryHash = "d86775d0ef16a63a33ad52e80eaff963b2d5b72fada7c991504a57496e1d8e4b"
	streamHash    = "198492e0857f6aedead9665c81c5a06d67b25b58034649687124083ff288597d"
	claimHash     = "a455deea71bdc9015b78eb49f4acfbce8baa7ccbedd28e549bb025bd0f751930"
)

type Account struct {
	Login string `json:"login"`
	Token string `json:"token"`
}
type Proxy struct {
	Scheme   string `json:"scheme"`
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Username string `json:"username"`
	Password string `json:"password"`
}
type Config struct {
	ConnectionTimeout     int `json:"connection_timeout"`
	RetryDelay            int `json:"retry_delay"`
	MaxRetries            int `json:"max_retries"`
	WatchInterval         int `json:"watch_interval"`
	InventoryRefresh      int `json:"inventory_refresh"`
	InventoryCheckMinutes int `json:"inventory_check_minutes"`
	OfflineCheckInterval  int `json:"offline_check_interval"`
}
type Job struct {
	OwnerID   int       `json:"owner_id"`
	Accounts  []Account `json:"accounts"`
	Proxies   []Proxy   `json:"proxies"`
	Streamers []string  `json:"streamers"`
	Config    Config    `json:"config"`
	Stagger   float64   `json:"stagger"`
}
type Event struct {
	Type         string        `json:"type"`
	Login        string        `json:"login,omitempty"`
	Level        string        `json:"level,omitempty"`
	Message      string        `json:"message,omitempty"`
	CurrentGame  *string       `json:"current_game"`
	WatchMinutes int           `json:"watch_minutes"`
	Progress     []ProgressRow `json:"progress,omitempty"`
}
type ProgressRow struct {
	Campaign string `json:"campaign"`
	Drop     string `json:"drop"`
	GameID   string `json:"game_id"`
	GameName string `json:"game_name"`
	Current  int    `json:"current"`
	Required int    `json:"required"`
	Status   string `json:"status"`
}
type Drop struct {
	ID       string
	Name     string
	GameID   string
	GameName string
	Campaign string
	Required int
	Current  int
	Claimed  bool
	ClaimID  string
}

func (d *Drop) CanEarn() bool  { return !d.Claimed && d.Current < d.Required }
func (d *Drop) CanClaim() bool { return !d.Claimed && d.Current >= d.Required && d.ClaimID != "" }
func (d *Drop) Status() string {
	if d.Claimed {
		return "claimed"
	}
	if d.ClaimID != "" {
		return "ready"
	}
	return "in_progress"
}

type Game struct {
	ID   string
	Name string
}
type Channel struct {
	ID      string
	Login   string
	Name    string
	Viewers int
	Game    *Game
}

type Miner struct {
	job          Job
	account      Account
	client       *http.Client
	deviceID     string
	sessionID    string
	userID       string
	username     string
	streamers    []string
	running      bool
	currentGame  *string
	watchMinutes int
	watching     *Channel
	active       map[string]*Drop
	claimed      map[string]bool
	spade        map[string]string
	proxy        *Proxy
	pubsub       *websocket.Conn
	emit         func(Event)
	lastProg     string
	mu           sync.RWMutex
}

var outMu sync.Mutex

func emit(e Event) {
	outMu.Lock()
	defer outMu.Unlock()
	b, _ := json.Marshal(e)
	os.Stdout.Write(b)
	os.Stdout.Write([]byte("\n"))
}
func logEvent(login, level, message string, emitFn func(Event)) {
	if len(message) > 500 {
		message = message[:500]
	}
	emitFn(Event{Type: "log", Login: login, Level: level, Message: message})
}
func randomHex(n int) string {
	b := make([]byte, n/2)
	if _, err := rand.Read(b); err != nil {
		return strings.Repeat("0", n)
	}
	return hex.EncodeToString(b)
}
func proxyURL(p *Proxy) *url.URL {
	if p == nil || p.Host == "" || p.Port == 0 {
		return nil
	}
	scheme := p.Scheme
	if scheme == "" {
		scheme = "http"
	}
	u, err := url.Parse(fmt.Sprintf("%s://%s:%d", scheme, p.Host, p.Port))
	if err != nil {
		return nil
	}
	if p.Username != "" {
		u.User = url.UserPassword(p.Username, p.Password)
	}
	return u
}
func newClient(p *Proxy, timeout int) *http.Client {
	tr := &http.Transport{}
	if u := proxyURL(p); u != nil {
		tr.Proxy = http.ProxyURL(u)
	}
	jar, _ := cookiejar.New(nil)
	return &http.Client{Transport: tr, Timeout: time.Duration(timeout) * time.Second, Jar: jar}
}
func (m *Miner) request(ctx context.Context, method, target string, body []byte, headers http.Header) ([]byte, int, error) {
	req, err := http.NewRequestWithContext(ctx, method, target, bytes.NewReader(body))
	if err != nil {
		return nil, 0, err
	}
	for k, vv := range headers {
		for _, v := range vv {
			req.Header.Add(k, v)
		}
	}
	resp, err := m.client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	return data, resp.StatusCode, err
}
func (m *Miner) baseHeaders() http.Header {
	h := http.Header{"Accept": []string{"*/*"}, "Accept-Language": []string{"en-US"}, "Authorization": []string{"OAuth " + m.account.Token}, "Client-Id": []string{clientID}, "Client-Session-Id": []string{m.sessionID}, "User-Agent": []string{userAgent}, "X-Device-Id": []string{m.deviceID}, "Origin": []string{"https://www.twitch.tv"}, "Referer": []string{"https://www.twitch.tv/"}}
	return h
}
func (m *Miner) bootstrap(ctx context.Context) {
	h := http.Header{"Accept-Language": []string{"en-US"}, "User-Agent": []string{userAgent}}
	_, _, err := m.request(ctx, http.MethodGet, "https://www.twitch.tv", nil, h)
	if err != nil {
		return
	}
	if m.client.Jar != nil {
		for _, c := range m.client.Jar.Cookies(&url.URL{Scheme: "https", Host: "www.twitch.tv"}) {
			if c.Name == "unique_id" && regexp.MustCompile(`^[a-z0-9]{16,64}$`).MatchString(c.Value) {
				m.deviceID = c.Value
				return
			}
		}
	}
}
func (m *Miner) gql(ctx context.Context, op map[string]any) (map[string]any, error) {
	body, err := json.Marshal([]any{op})
	if err != nil {
		return nil, err
	}
	headers := m.baseHeaders()
	headers.Set("Content-Type", "application/json")
	data, status, err := m.request(ctx, http.MethodPost, gqlURL, body, headers)
	if err != nil || status < 200 || status >= 300 {
		return nil, errors.New("gql request failed")
	}
	var rows []map[string]any
	if json.Unmarshal(data, &rows) != nil || len(rows) == 0 {
		return nil, errors.New("gql response invalid")
	}
	if es, ok := rows[0]["errors"].([]any); ok && len(es) > 0 {
		return nil, errors.New("gql response error")
	}
	return rows[0], nil
}
func (m *Miner) validate(ctx context.Context) bool {
	data, status, err := m.request(ctx, http.MethodGet, validateURL, nil, http.Header{"Authorization": []string{"OAuth " + m.account.Token}})
	if err != nil {
		logEvent(m.account.Login, "warn", "не удалось проверить аккаунт", m.emit)
		return false
	}
	if status == http.StatusUnauthorized {
		logEvent(m.account.Login, "warn", "аккаунт невалиден: токен отклонён", m.emit)
		return false
	}
	var v map[string]any
	if json.Unmarshal(data, &v) != nil {
		logEvent(m.account.Login, "warn", "не удалось проверить аккаунт", m.emit)
		return false
	}
	if id, ok := v["user_id"].(string); ok {
		m.userID = id
	} else if id, ok := v["user_id"].(float64); ok {
		m.userID = strconv.FormatInt(int64(id), 10)
	}
	m.username, _ = v["login"].(string)
	if m.username == "" {
		m.username = m.account.Login
	}
	return true
}
func (m *Miner) inventory(ctx context.Context) {
	op := map[string]any{"operationName": "Inventory", "variables": map[string]any{"fetchRewardCampaigns": false}, "extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": inventoryHash}}}
	res, err := m.gql(ctx, op)
	if err != nil {
		logEvent(m.account.Login, "warn", "не удалось обновить данные аккаунта", m.emit)
		return
	}
	data := mapData(res["data"])
	inv := mapData(mapData(data["currentUser"])["inventory"])
	campaigns, _ := mapSlice(inv["dropCampaignsInProgress"])
	now := time.Now().UTC()
	next := map[string]*Drop{}
	for _, raw := range campaigns {
		c := mapData(raw)
		if c["status"] == "EXPIRED" {
			continue
		}
		if t, ok := parseTime(c["endAt"]); ok && t.Before(now) {
			continue
		}
		if t, ok := parseTime(c["startAt"]); ok && t.After(now.Add(24*time.Hour)) {
			continue
		}
		campaignName, _ := c["name"].(string)
		game := mapData(c["game"])
		gameID, _ := game["id"].(string)
		gameName, _ := game["name"].(string)
		drops, _ := mapSlice(c["timeBasedDrops"])
		for _, rd := range drops {
			d := mapData(rd)
			id, _ := d["id"].(string)
			name, _ := d["name"].(string)
			req := intNum(d["requiredMinutesWatched"])
			self := mapData(d["self"])
			cur := intNum(self["currentMinutesWatched"])
			claimed, _ := self["isClaimed"].(bool)
			cid, _ := self["dropInstanceID"].(string)
			drop := &Drop{ID: id, Name: name, GameID: gameID, GameName: gameName, Campaign: campaignName, Required: req, Current: cur, Claimed: claimed, ClaimID: cid}
			if (drop.CanEarn() || drop.CanClaim()) && !m.claimed[cid] {
				next[id] = drop
			}
		}
	}
	m.mu.Lock()
	m.active = next
	m.mu.Unlock()
	m.claimCompleted(ctx)
}

func (m *Miner) hasEarnableGame(gameID string) bool {
	if gameID == "" {
		return false
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	for _, d := range m.active {
		if d.CanEarn() && d.GameID == gameID {
			return true
		}
	}
	return false
}
func (m *Miner) claimCompleted(ctx context.Context) {
	m.mu.RLock()
	drops := make([]*Drop, 0)
	for _, d := range m.active {
		if d.CanClaim() && d.ClaimID != "" && !m.claimed[d.ClaimID] {
			drops = append(drops, d)
		}
	}
	m.mu.RUnlock()
	for _, d := range drops {
		op := map[string]any{"operationName": "DropsPage_ClaimDropRewards", "variables": map[string]any{"input": map[string]any{"dropInstanceID": d.ClaimID}}, "extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": claimHash}}}
		res, err := m.gql(ctx, op)
		if err != nil {
			continue
		}
		claim := mapData(mapData(res["data"])["claimDropRewards"])
		status, _ := claim["status"].(string)
		if status == "ELIGIBLE_FOR_ALL" || status == "DROP_INSTANCE_ALREADY_CLAIMED" {
			m.mu.Lock()
			m.claimed[d.ClaimID] = true
			delete(m.active, d.ID)
			m.mu.Unlock()
			logEvent(m.account.Login, "info", "дроп заклеймлен: "+d.Name, m.emit)
		}
	}
}

// claimPending забирает все готовые награды из инвентаря при старте фарма,
// включая дропы завершившихся кампаний, которые inventory отсеивает по датам.
func (m *Miner) claimPending(ctx context.Context) {
	op := map[string]any{"operationName": "Inventory", "variables": map[string]any{"fetchRewardCampaigns": false}, "extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": inventoryHash}}}
	res, err := m.gql(ctx, op)
	if err != nil {
		logEvent(m.account.Login, "warn", "не удалось проверить готовые к клейму дропы", m.emit)
		return
	}
	inv := mapData(mapData(mapData(res["data"])["currentUser"])["inventory"])
	campaigns, _ := mapSlice(inv["dropCampaignsInProgress"])
	type pending struct{ id, name string }
	var todo []pending
	for _, raw := range campaigns {
		drops, _ := mapSlice(mapData(raw)["timeBasedDrops"])
		for _, rd := range drops {
			d := mapData(rd)
			self := mapData(d["self"])
			cid, _ := self["dropInstanceID"].(string)
			claimed, _ := self["isClaimed"].(bool)
			if cid == "" || claimed {
				continue
			}
			m.mu.RLock()
			done := m.claimed[cid]
			m.mu.RUnlock()
			if done {
				continue
			}
			name, _ := d["name"].(string)
			todo = append(todo, pending{cid, name})
		}
	}
	if len(todo) == 0 {
		logEvent(m.account.Login, "info", "готовых к клейму дропов нет", m.emit)
		return
	}
	logEvent(m.account.Login, "info", fmt.Sprintf("готовых к клейму дропов: %d, забираю", len(todo)), m.emit)
	for _, p := range todo {
		op := map[string]any{"operationName": "DropsPage_ClaimDropRewards", "variables": map[string]any{"input": map[string]any{"dropInstanceID": p.id}}, "extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": claimHash}}}
		res, err := m.gql(ctx, op)
		if err != nil {
			continue
		}
		status, _ := mapData(mapData(res["data"])["claimDropRewards"])["status"].(string)
		if status == "ELIGIBLE_FOR_ALL" || status == "DROP_INSTANCE_ALREADY_CLAIMED" {
			m.mu.Lock()
			m.claimed[p.id] = true
			m.mu.Unlock()
			logEvent(m.account.Login, "info", "дроп заклеймлен: "+p.name, m.emit)
		} else {
			logEvent(m.account.Login, "warn", "не удалось забрать дроп "+p.name+": Twitch отклонил клейм", m.emit)
		}
	}
}

func (m *Miner) streamInfo(ctx context.Context, login string) (*Channel, error) {
	op := map[string]any{"operationName": "VideoPlayerStreamInfoOverlayChannel", "variables": map[string]any{"channel": login}, "extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": streamHash}}}
	res, err := m.gql(ctx, op)
	if err != nil {
		return nil, err
	}
	user := mapData(mapData(res["data"])["user"])
	if user == nil {
		logEvent(m.account.Login, "info", "стример "+login+" не найден", m.emit)
		return nil, nil
	}
	stream := mapData(user["stream"])
	if stream == nil {
		logEvent(m.account.Login, "info", "стример "+login+" офлайн", m.emit)
		return nil, nil
	}
	id, _ := user["id"].(string)
	if id == "" {
		id, _ = stream["id"].(string)
	}
	display, _ := user["displayName"].(string)
	if display == "" {
		display = login
	}
	game := mapData(stream["game"])
	g := &Game{}
	if game != nil {
		g.ID, _ = game["id"].(string)
		g.Name, _ = game["name"].(string)
	}
	if g.Name == "" {
		if fallback, fallbackErr := m.streamGame(ctx, login); fallbackErr == nil {
			g = fallback
		}
	}
	channel := &Channel{ID: id, Login: login, Name: display, Viewers: intNum(stream["viewersCount"]), Game: g}
	logEvent(m.account.Login, "info", fmt.Sprintf("стример %s онлайн (%d зрителей), игра: %s", display, channel.Viewers, gameName(channel)), m.emit)
	return channel, nil
}
func (m *Miner) streamGame(ctx context.Context, login string) (*Game, error) {
	q := `query { user(login: "` + strings.ReplaceAll(login, `"`, `\"`) + `") { stream { id game { id name } } } }`
	res, err := m.gql(ctx, map[string]any{"query": q})
	if err != nil {
		return nil, err
	}
	game := mapData(mapData(mapData(mapData(res["data"])["user"])["stream"])["game"])
	if game == nil {
		return nil, errors.New("no game")
	}
	g := &Game{}
	g.ID, _ = game["id"].(string)
	g.Name, _ = game["name"].(string)
	return g, nil
}
func (m *Miner) watch(ctx context.Context, ch *Channel) {
	m.mu.Lock()
	m.watching = ch
	m.watchMinutes = 0
	m.currentGame = nil
	m.mu.Unlock()
	bid := ch.ID
	if bid == "" {
		logEvent(m.account.Login, "warn", "стример "+ch.Name+" недоступен, просмотр не начат", m.emit)
		return
	}
	spade := m.getSpade(ctx, ch.Login)
	if ch.Game != nil {
		g := ch.Game.Name
		m.mu.Lock()
		m.currentGame = &g
		m.mu.Unlock()
	}
	logEvent(m.account.Login, "info", fmt.Sprintf("смотрю %s: играет %s", ch.Name, gameName(ch)), m.emit)
	last := time.Now()
	snap := m.snapshot()
	for m.isRunning() {
		if m.watchMinutes > 0 && m.watchMinutes%15 == 0 {
			if fresh, _ := m.streamInfo(ctx, ch.Login); fresh != nil && fresh.ID != bid {
				bid = fresh.ID
				ch = fresh
				spade = m.getSpade(ctx, ch.Login)
			}
		}
		if m.sendProgress(ctx, ch, bid, spade) {
			m.mu.Lock()
			m.watchMinutes++
			mins := m.watchMinutes
			m.mu.Unlock()
			logEvent(m.account.Login, "info", fmt.Sprintf("смотрю %s: %d мин", ch.Name, mins), m.emit)
		}
		checkMinutes := max(1, m.config().InventoryCheckMinutes)
		if m.watchMinutes > 0 && m.watchMinutes%checkMinutes == 0 {
			m.inventory(ctx)
			cur := m.snapshot()
			if advanced(snap, cur) {
				snap = cur
				last = time.Now()
			} else if time.Since(last) >= 20*time.Minute {
				logEvent(m.account.Login, "warn", "прогресс не меняется 20 минут, выбираю другого стримера", m.emit)
				break
			}
		}
		if online, _ := m.streamInfo(ctx, ch.Login); online == nil {
			logEvent(m.account.Login, "info", "офлайн, просмотр остановлен", m.emit)
			break
		}
		time.Sleep(time.Duration(max(1, m.config().WatchInterval)) * time.Second)
	}
	m.mu.Lock()
	m.watching = nil
	m.currentGame = nil
	m.mu.Unlock()
	logEvent(m.account.Login, "info", fmt.Sprintf("просмотр %s завершён, всего %d мин", ch.Name, m.watchMinutes), m.emit)
}
func (m *Miner) config() Config  { return m.job.Config }
func (m *Miner) isRunning() bool { m.mu.RLock(); defer m.mu.RUnlock(); return m.running }
func (m *Miner) snapshot() map[string]int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	r := map[string]int{}
	for id, d := range m.active {
		if d.CanEarn() {
			r[id] = d.Current
		}
	}
	return r
}
func (m *Miner) progressRows() []ProgressRow {
	m.mu.RLock()
	defer m.mu.RUnlock()
	rows := make([]ProgressRow, 0, len(m.active))
	for _, d := range m.active {
		rows = append(rows, ProgressRow{
			Campaign: d.Campaign,
			Drop:     d.Name,
			GameID:   d.GameID,
			GameName: d.GameName,
			Current:  d.Current,
			Required: d.Required,
			Status:   d.Status(),
		})
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].GameID != rows[j].GameID {
			return rows[i].GameID < rows[j].GameID
		}
		if rows[i].Campaign != rows[j].Campaign {
			return rows[i].Campaign < rows[j].Campaign
		}
		return rows[i].Drop < rows[j].Drop
	})
	return rows
}
func advanced(a, b map[string]int) bool {
	if len(b) < len(a) {
		return true
	}
	for k, v := range a {
		if b[k] > v {
			return true
		}
	}
	return false
}
func (m *Miner) getSpade(ctx context.Context, login string) string {
	m.mu.RLock()
	v := m.spade[login]
	m.mu.RUnlock()
	if v != "" {
		return v
	}
	data, _, err := m.request(ctx, http.MethodGet, "https://www.twitch.tv/"+url.PathEscape(login), nil, http.Header{"User-Agent": []string{userAgent}})
	if err != nil {
		return ""
	}
	re := regexp.MustCompile(`"spade_?url"\s*:\s*"(https://[^"]+)"`)
	match := re.FindSubmatch(data)
	if len(match) <= 1 {
		js := regexp.MustCompile(`src="(https://[^"]+/config/settings\.[a-f0-9]{32}\.js)"`).FindSubmatch(data)
		if len(js) > 1 {
			script, _, scriptErr := m.request(ctx, http.MethodGet, string(js[1]), nil, http.Header{"User-Agent": []string{userAgent}})
			if scriptErr == nil {
				match = re.FindSubmatch(script)
			}
		}
	}
	if len(match) > 1 {
		v = string(match[1])
		m.mu.Lock()
		m.spade[login] = v
		m.mu.Unlock()
	}
	return v
}
func (m *Miner) sendProgress(ctx context.Context, ch *Channel, bid, spade string) bool {
	gname, gid := "", ""
	if ch.Game != nil {
		gname = ch.Game.Name
		gid = ch.Game.ID
	}
	uid, _ := strconv.Atoi(m.userID)
	props := map[string]any{"broadcast_id": bid, "channel_id": ch.ID, "channel": ch.Login, "client_time": time.Now().UTC().Format("2006-01-02T15:04:05.000Z"), "game": gname, "game_id": gid, "hidden": false, "is_live": true, "live": true, "logged_in": true, "minutes_logged": 1, "muted": false, "user_id": uid}
	raw, _ := json.Marshal([]any{map[string]any{"event": "minute-watched", "properties": props}})
	enc := base64.StdEncoding.EncodeToString(raw)
	if spade != "" {
		data, status, err := m.request(ctx, http.MethodPost, spade, []byte("data="+url.QueryEscape(enc)), http.Header{"Content-Type": []string{"application/x-www-form-urlencoded"}})
		_ = data
		if err == nil && (status == 200 || status == 204) {
			return true
		}
	}
	var gz bytes.Buffer
	zw := gzip.NewWriter(&gz)
	_, _ = zw.Write(raw)
	_ = zw.Close()
	op := map[string]any{"operationName": "SendEvents", "variables": map[string]any{"input": map[string]any{"data": base64.StdEncoding.EncodeToString(gz.Bytes()), "repository": "twilight", "encoding": "GZIP_B64"}}, "query": "mutation SendEvents($input: SendSpadeEventsInput!) { sendSpadeEvents(input: $input) { statusCode } }"}
	res, err := m.gql(ctx, op)
	if err != nil {
		return false
	}
	code := intNum(mapData(mapData(res["data"])["sendSpadeEvents"])["statusCode"])
	return code == 200 || code == 204
}
func (m *Miner) pubsubLoop(ctx context.Context) {
	for m.isRunning() {
		dialer := websocket.DefaultDialer
		if u := proxyURL(m.proxy); u != nil {
			dialer = &websocket.Dialer{Proxy: http.ProxyURL(u), HandshakeTimeout: 15 * time.Second}
		}
		conn, _, err := dialer.DialContext(ctx, "wss://pubsub-edge.twitch.tv/v1", nil)
		if err != nil {
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
				continue
			}
		}
		m.mu.Lock()
		m.pubsub = conn
		m.mu.Unlock()
		topics := []string{"user-drop-events." + m.userID, "onsite-notifications." + m.userID}
		_ = conn.WriteJSON(map[string]any{"type": "LISTEN", "data": map[string]any{"topics": topics, "auth_token": m.account.Token}})
		stopPing := make(chan struct{})
		go func() {
			t := time.NewTicker(180 * time.Second)
			defer t.Stop()
			for {
				select {
				case <-stopPing:
					return
				case <-ctx.Done():
					return
				case <-t.C:
					_ = conn.WriteJSON(map[string]any{"type": "PING"})
				}
			}
		}()
		for {
			var msg map[string]any
			if err := conn.ReadJSON(&msg); err != nil {
				break
			}
			typ, _ := msg["type"].(string)
			if typ == "RECONNECT" {
				break
			}
			if typ != "MESSAGE" {
				continue
			}
			data := mapData(msg["data"])
			topic, _ := data["topic"].(string)
			if !strings.Contains(topic, "user-drop-events") {
				continue
			}
			text, _ := data["message"].(string)
			var drop map[string]any
			if json.Unmarshal([]byte(text), &drop) != nil {
				continue
			}
			kind, _ := drop["type"].(string)
			if kind == "drop-progress" {
				id, _ := drop["drop_id"].(string)
				m.mu.Lock()
				if d := m.active[id]; d != nil {
					d.Current = intNum(drop["current_progress_min"])
				}
				m.mu.Unlock()
			} else if kind == "drop-claim" {
				payload := mapData(drop["data"])
				id, _ := payload["drop_id"].(string)
				instance, _ := payload["drop_instance_id"].(string)
				m.mu.Lock()
				d := m.active[id]
				if d != nil {
					d.ClaimID = instance
				}
				m.mu.Unlock()
				if d != nil {
					go m.claimOne(context.Background(), d)
				}
			}
		}
		close(stopPing)
		_ = conn.Close()
		m.mu.Lock()
		m.pubsub = nil
		m.mu.Unlock()
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Second):
		}
	}
}
func (m *Miner) claimOne(ctx context.Context, d *Drop) {
	m.mu.RLock()
	already := m.claimed[d.ClaimID]
	m.mu.RUnlock()
	if already || d.ClaimID == "" {
		return
	}
	op := map[string]any{"operationName": "DropsPage_ClaimDropRewards", "variables": map[string]any{"input": map[string]any{"dropInstanceID": d.ClaimID}}, "extensions": map[string]any{"persistedQuery": map[string]any{"version": 1, "sha256Hash": claimHash}}}
	res, err := m.gql(ctx, op)
	if err != nil {
		return
	}
	status, _ := mapData(mapData(res["data"])["claimDropRewards"])["status"].(string)
	if status == "ELIGIBLE_FOR_ALL" || status == "DROP_INSTANCE_ALREADY_CLAIMED" {
		m.mu.Lock()
		m.claimed[d.ClaimID] = true
		delete(m.active, d.ID)
		m.mu.Unlock()
		logEvent(m.account.Login, "info", "дроп заклеймлен: "+d.Name, m.emit)
	}
}
func (m *Miner) run(ctx context.Context) {
	defer func() {
		if recover() != nil {
			logEvent(m.account.Login, "error", "ошибка основного цикла фарма", m.emit)
		}
	}()
	m.bootstrap(ctx)
	if !m.validate(ctx) {
		return
	}
	go m.pubsubLoop(ctx)
	m.inventory(ctx)
	m.claimPending(ctx)
	idx := 0
	for m.isRunning() {
		if len(m.streamers) == 0 {
			time.Sleep(time.Duration(max(1, m.config().OfflineCheckInterval)) * time.Second)
			m.inventory(ctx)
			continue
		}
		logEvent(m.account.Login, "info", "фармлю дропы, ищу онлайн-стримера", m.emit)
		found := false
		for n := 0; n < len(m.streamers); n++ {
			if !m.isRunning() {
				break
			}
			s := m.streamers[(idx+n)%len(m.streamers)]
			ch, _ := m.streamInfo(ctx, s)
			if ch != nil {
				idx = (idx + n + 1) % len(m.streamers)
				m.watch(ctx, ch)
				found = true
				break
			}
		}
		if !found {
			logEvent(m.account.Login, "info", fmt.Sprintf("онлайн-стримеров из кампании нет, жду %d секунд", max(1, m.config().OfflineCheckInterval)), m.emit)
			time.Sleep(time.Duration(max(1, m.config().OfflineCheckInterval)) * time.Second)
			idx = 0
		}
	}
}
func (m *Miner) start(ctx context.Context) {
	m.mu.Lock()
	m.running = true
	m.mu.Unlock()
	go m.run(ctx)
}
func mapData(v any) map[string]any { m, _ := v.(map[string]any); return m }
func mapSlice(v any) ([]any, bool) { s, ok := v.([]any); return s, ok }
func intNum(v any) int {
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case string:
		i, _ := strconv.Atoi(n)
		return i
	}
	return 0
}
func parseTime(v any) (time.Time, bool) {
	s, ok := v.(string)
	if !ok {
		return time.Time{}, false
	}
	for _, f := range []string{"2006-01-02T15:04:05.999999Z", "2006-01-02T15:04:05Z"} {
		if t, e := time.Parse(f, s); e == nil {
			return t, true
		}
	}
	return time.Time{}, false
}
func gameName(c *Channel) string {
	if c.Game == nil {
		return "неизвестная игра"
	}
	return c.Game.Name
}

func publisher(ctx context.Context, miners []*Miner) {
	t := time.NewTicker(time.Second)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			for _, m := range miners {
				m.mu.RLock()
				g := m.currentGame
				w := m.watchMinutes
				login := m.account.Login
				m.mu.RUnlock()
				m.emit(Event{Type: "card", Login: login, CurrentGame: g, WatchMinutes: w})
				rows := m.progressRows()
				if len(rows) > 0 {
					if b, err := json.Marshal(rows); err == nil {
						if key := string(b); key != m.lastProg {
							m.lastProg = key
							m.emit(Event{Type: "progress", Login: login, Progress: rows})
						}
					}
				}
			}
		}
	}
}
func main() {
	// Become a session leader. Failure is harmless when already isolated.
	_, _, _ = syscall.Syscall(syscall.SYS_SETSID, 0, 0, 0)
	var job Job
	if err := json.NewDecoder(os.Stdin).Decode(&job); err != nil {
		return
	}
	ctx, cancel := signal.NotifyContext(
		context.Background(), syscall.SIGTERM, syscall.SIGINT,
	)
	defer cancel()

	miners := make([]*Miner, 0, len(job.Accounts))
	for i, account := range job.Accounts {
		var proxy *Proxy
		if len(job.Proxies) > 0 {
			selected := job.Proxies[i%len(job.Proxies)]
			proxy = &selected
		}
		miner := &Miner{
			job:       job,
			account:   account,
			proxy:     proxy,
			client:    newClient(proxy, max(1, job.Config.ConnectionTimeout)),
			deviceID:  randomHex(32),
			sessionID: randomHex(16),
			streamers: job.Streamers,
			active:    map[string]*Drop{},
			claimed:   map[string]bool{},
			spade:     map[string]string{},
			emit:      emit,
		}
		miners = append(miners, miner)
		logEvent(
			"system", "info",
			fmt.Sprintf("starting miner for %s (%d/%d)", account.Login, i+1, len(job.Accounts)),
			emit,
		)
		miner.start(ctx)
		if job.Stagger > 0 && i < len(job.Accounts)-1 {
			select {
			case <-ctx.Done():
			case <-time.After(time.Duration(job.Stagger * float64(time.Second))):
			}
		}
	}
	go publisher(ctx, miners)
	<-ctx.Done()
	for _, miner := range miners {
		miner.mu.Lock()
		miner.running = false
		if miner.pubsub != nil {
			_ = miner.pubsub.Close()
		}
		miner.mu.Unlock()
	}
	time.Sleep(100 * time.Millisecond)
}
func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
