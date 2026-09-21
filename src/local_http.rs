//! Bounded loopback HTTP connection lifetimes shared by local services.
use std::{
    future::Future,
    io,
    net::SocketAddr,
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
    time::Duration,
};
use tokio::{
    io::{AsyncRead, AsyncWrite, ReadBuf},
    net::{TcpListener, TcpStream},
    sync::{OwnedSemaphorePermit, Semaphore},
    time::Sleep,
};
// Limit accepted connection tasks, including peers that never finish headers.
// Every connection has an absolute lifetime, including header/body I/O.
pub struct BoundedListener {
    socket: TcpListener,
    slots: Arc<Semaphore>,
    lifetime: Duration,
}
pub struct BoundedIo {
    socket: TcpStream,
    _permit: OwnedSemaphorePermit,
    timer: Pin<Box<Sleep>>,
}
impl BoundedIo {
    fn expired(&mut self, cx: &mut Context<'_>) -> bool {
        self.timer.as_mut().poll(cx).is_ready()
    }
}
fn expired_error() -> io::Error {
    io::Error::new(io::ErrorKind::TimedOut, "connection lifetime exceeded")
}
impl AsyncRead for BoundedIo {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if self.expired(cx) {
            return Poll::Ready(Err(expired_error()));
        }
        Pin::new(&mut self.socket).poll_read(cx, buf)
    }
}
impl AsyncWrite for BoundedIo {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &[u8],
    ) -> Poll<io::Result<usize>> {
        if self.expired(cx) {
            return Poll::Ready(Err(expired_error()));
        }
        Pin::new(&mut self.socket).poll_write(cx, buf)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.expired(cx) {
            return Poll::Ready(Err(expired_error()));
        }
        Pin::new(&mut self.socket).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.socket).poll_shutdown(cx)
    }
}
impl axum::serve::Listener for BoundedListener {
    type Io = BoundedIo;
    type Addr = SocketAddr;
    async fn accept(&mut self) -> (Self::Io, Self::Addr) {
        loop {
            let permit = self
                .slots
                .clone()
                .acquire_owned()
                .await
                .expect("private connection semaphore");
            match self.socket.accept().await {
                Ok((socket, addr)) => {
                    return (
                        BoundedIo {
                            socket,
                            _permit: permit,
                            timer: Box::pin(tokio::time::sleep(self.lifetime)),
                        },
                        addr,
                    );
                }
                Err(_) => tokio::time::sleep(Duration::from_millis(100)).await,
            }
        }
    }
    fn local_addr(&self) -> io::Result<Self::Addr> {
        self.socket.local_addr()
    }
}

impl BoundedListener {
    pub fn new(socket: TcpListener, capacity: usize, lifetime: Duration) -> Self {
        Self {
            socket,
            slots: Arc::new(Semaphore::new(capacity)),
            lifetime,
        }
    }
}
