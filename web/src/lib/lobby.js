// The lobby socket (/ws/lobby, astrum/lobby.py): every lobby and level as the server pushes them,
// and this user's actions back on it. Opened once signed in; open again a second after it drops.
export class LobbySocket {
  constructor(onstate, onerror) {
    this.onstate = onstate;
    this.onerror = onerror;
    this.closed = false;
    this._open();
  }
  _open() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.ws = new WebSocket(`${proto}://${location.host}/ws/lobby`);
    this.ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.kind === 'error') this.onerror(m.detail); else this.onstate(m);
    };
    this.ws.onclose = () => { if (!this.closed) setTimeout(() => this._open(), 1000); };
  }
  // { do: 'make' | 'join' | 'leave' | 'side' | 'level' | 'start' | 'run' | 'pause' | 'warp' | 'restart' | 'stop', ... }
  send(msg) {
    if (this.ws.readyState === 1) this.ws.send(JSON.stringify(msg));
    else this.onerror('Not connected to the lobby: trying again');
  }
  close() { this.closed = true; this.ws.close(); }
}
