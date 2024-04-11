-- CreateEnum
CREATE TYPE "SessionState" AS ENUM ('STARTING', 'IN_PROGRESS', 'PROCESSING', 'FINISHED');

-- CreateTable
CREATE TABLE "TrackingSession" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "state" "SessionState" NOT NULL,
    "timeout" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "TrackingSession_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TrackingAudioChunk" (
    "sessionId" TEXT NOT NULL,
    "index" INTEGER NOT NULL,
    "format" TEXT NOT NULL,
    "data" BYTEA NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE UNIQUE INDEX "TrackingAudioChunk_sessionId_index_key" ON "TrackingAudioChunk"("sessionId", "index");

-- AddForeignKey
ALTER TABLE "TrackingSession" ADD CONSTRAINT "TrackingSession_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TrackingAudioChunk" ADD CONSTRAINT "TrackingAudioChunk_sessionId_fkey" FOREIGN KEY ("sessionId") REFERENCES "TrackingSession"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
